from datetime import datetime
from flask import (Flask, render_template, request, jsonify,
                   session, redirect, url_for, abort)
from functools import wraps
import mysql.connector
import os
import hashlib
import hmac
import secrets

try:
    from .gigachat_service import ask_gigachat
except ImportError:
    from gigachat_service import ask_gigachat

app = Flask(__name__)
app.secret_key = "change-me-to-a-random-long-string"

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "database": "sch688_vvedenie",
    "user": "root",
    "password": "",
    "autocommit": True,
}

DEFAULT_AI_PRICE = 3

# ---------- Хеширование паролей (pbkdf2, без префиксов) ----------
PBKDF2_ITERATIONS = 600_000
PBKDF2_KEYLEN     = 32
PBKDF2_HASH       = "sha256"
SALT_BYTES        = 16


def hash_password(password: str) -> str:
    """Возвращает 'hex_хеш:hex_соль' — без служебных префиксов."""
    salt = secrets.token_bytes(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(
        PBKDF2_HASH,
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=PBKDF2_KEYLEN,
    )
    return f"{dk.hex()}:{salt.hex()}"


def verify_password(stored: str, password: str) -> bool:
    """Поддерживает новый формат 'hex:hex' и старые хеши werkzeug."""
    if not stored:
        return False

    # Новый формат: hex_хеш:hex_соль (двоеточие, без $)
    if ":" in stored and "$" not in stored:
        try:
            hash_hex, salt_hex = stored.split(":", 1)
            salt = bytes.fromhex(salt_hex)
        except (ValueError, AttributeError):
            return False
        dk = hashlib.pbkdf2_hmac(
            PBKDF2_HASH,
            password.encode("utf-8"),
            salt,
            PBKDF2_ITERATIONS,
            dklen=PBKDF2_KEYLEN,
        )
        return hmac.compare_digest(dk.hex(), hash_hex)

    # Старые хеши werkzeug (scrypt:, pbkdf2:) — на случай миграции
    try:
        from werkzeug.security import check_password_hash
        return check_password_hash(stored, password)
    except Exception:
        return False


def get_ai_price():
    """Читает цену запроса из БД. Если что-то не так — возвращает дефолт."""
    try:
        cnx = get_db()
        cur = cnx.cursor(dictionary=True)
        cur.execute("SELECT `value` FROM settings WHERE `key` = 'ai_price'")
        row = cur.fetchone()
        cur.close(); cnx.close()
        return int(row["value"]) if row else DEFAULT_AI_PRICE
    except Exception:
        return DEFAULT_AI_PRICE


def set_ai_price(new_price):
    cnx = get_db()
    cur = cnx.cursor()
    cur.execute(
        "INSERT INTO settings (`key`, `value`) VALUES ('ai_price', %s) "
        "ON DUPLICATE KEY UPDATE `value` = VALUES(`value`)",
        (str(new_price),)
    )
    cnx.commit()
    cur.close(); cnx.close()


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


# ---------- Декораторы ----------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    """Только для админов. Проверяет флаг is_admin в БД (свежий)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))

        cnx = get_db()
        cur = cnx.cursor(dictionary=True)
        cur.execute("SELECT is_admin FROM users WHERE id = %s",
                    (session["user_id"],))
        row = cur.fetchone()
        cur.close(); cnx.close()

        if not row or not row["is_admin"]:
            abort(403)   # Forbidden
        return f(*args, **kwargs)
    return wrapper


# ---------- Страницы ----------
@app.route("/")
def registration():
    return render_template("registration.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/profile")
@login_required
def profile():
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)
    cur.execute(
        "SELECT username, surname, email, balance, is_admin "
        "FROM users WHERE id = %s",
        (session["user_id"],)
    )
    user = cur.fetchone()

    if user is None:
        cur.close(); cnx.close()
        session.clear()
        return redirect(url_for("login_page"))

    cur.execute(
        "SELECT id, amount, type, description, balance_after, "
        "DATE_FORMAT(created_at, '%d.%m.%Y %H:%i') as formatted_date "
        "FROM transactions WHERE user_id = %s ORDER BY id DESC",
        (session["user_id"],)
    )
    transactions = cur.fetchall()
    cur.close(); cnx.close()

    return render_template("profile.html", user=user, transactions=transactions)


@app.route("/api/transactions")
@login_required
def api_transactions():
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)
    cur.execute(
        "SELECT id, amount, type, description, balance_after, "
        "DATE_FORMAT(created_at, '%d.%m.%Y %H:%i') as formatted_date "
        "FROM transactions WHERE user_id = %s ORDER BY id DESC",
        (session["user_id"],)
    )
    rows = cur.fetchall()
    cur.close(); cnx.close()
    return jsonify({"status": "ok", "transactions": rows})


@app.route("/ai")
@login_required
def ai_page():
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)
    cur.execute("SELECT balance FROM users WHERE id = %s",
                (session["user_id"],))
    row = cur.fetchone()

    if row is None:
        cur.close(); cnx.close()
        session.clear()
        return redirect(url_for("login_page"))

    cur.execute(
        "SELECT id, role, content, file_url, file_type, file_name, "
        "DATE_FORMAT(created_at, '%H:%i') as time "
        "FROM chat_messages WHERE user_id = %s ORDER BY id ASC",
        (session["user_id"],)
    )
    messages = cur.fetchall()
    cur.close(); cnx.close()

    return render_template("ai.html",
                           balance=row["balance"],
                           price=get_ai_price(),
                           messages=messages)


@app.route("/api/chat/clear", methods=["POST"])
@login_required
def api_chat_clear():
    cnx = get_db()
    cur = cnx.cursor()
    cur.execute("DELETE FROM chat_messages WHERE user_id = %s", (session["user_id"],))
    cnx.commit()
    cur.close(); cnx.close()
    return jsonify({"status": "ok"})


# ---------- API регистрации / входа ----------
@app.route("/user_register", methods=["POST"])
def user_register():
    req = request.get_json() or {}
    name     = (req.get("name") or "").strip()
    lastname = (req.get("lastname") or "").strip() or None
    email    = (req.get("email") or "").strip().lower()
    password = req.get("password") or ""

    if not name or not email or not password:
        return jsonify({"status": "error",
                        "message": "Заполните все поля"}), 400

    password_hash = hash_password(password)

    cnx = get_db()
    cur = cnx.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    if cur.fetchone():
        cur.close(); cnx.close()
        return jsonify({"status": "error",
                        "message": "Пользователь с таким email уже существует"}), 400

    cur.execute(
        "INSERT INTO users (username, surname, email, password_hash) "
        "VALUES (%s, %s, %s, %s)",
        (name, lastname, email, password_hash)
    )
    new_user_id = cur.lastrowid
    cur.execute("SELECT balance FROM users WHERE id = %s", (new_user_id,))
    init_bal = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO transactions (user_id, amount, type, description, balance_after) "
        "VALUES (%s, %s, %s, %s, %s)",
        (new_user_id, init_bal, "initial", "Приветственный бонус", init_bal)
    )
    cnx.commit()
    cur.close(); cnx.close()
    return jsonify({"status": "ok", "redirect": "/login"})


@app.route("/user_login", methods=["POST"])
def user_login():
    req = request.get_json() or {}
    email    = (req.get("email") or "").strip().lower()
    password = req.get("password") or ""

    cnx = get_db()
    cur = cnx.cursor(dictionary=True)
    cur.execute(
        "SELECT id, username, password_hash, is_admin "
        "FROM users WHERE email = %s",
        (email,)
    )
    user = cur.fetchone()
    cur.close(); cnx.close()

    if not user or not verify_password(user["password_hash"], password):
        return jsonify({"status": "error",
                        "message": "Неверный email или пароль"}), 401

    session["user_id"]  = user["id"]
    session["username"] = user["username"]
    session["is_admin"] = bool(user["is_admin"])   # удобно для шаблонов

    # После входа всегда ведём в личный кабинет
    redirect_to = "/profile"
    return jsonify({"status": "ok", "redirect": redirect_to})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ---------- AI ----------
@app.route("/ai_request", methods=["POST"])
@login_required
def ai_request():
    prompt = ""
    file_path = None
    file_url = None
    file_type = None
    file_name = None
    mime_type = None

    if request.is_json:
        data = request.get_json() or {}
        prompt = (data.get("prompt") or "").strip()
    else:
        prompt = (request.form.get("prompt") or "").strip()
        if "file" in request.files:
            file = request.files["file"]
            if file and file.filename:
                orig_name = os.path.basename(file.filename)
                ext = os.path.splitext(orig_name)[1].lower()
                unique_name = f"{session['user_id']}_{secrets.token_hex(8)}{ext}"
                upload_dir = os.path.join(app.root_path, "static", "uploads")
                os.makedirs(upload_dir, exist_ok=True)
                save_path = os.path.join(upload_dir, unique_name)
                file.save(save_path)
                file_path = save_path
                file_url = f"/static/uploads/{unique_name}"
                file_name = orig_name
                mime_type = file.mimetype or "application/octet-stream"

                if ext in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"]:
                    file_type = "image"
                elif ext in [".mp3", ".wav", ".ogg", ".m4a", ".aac", ".weba"]:
                    file_type = "audio"
                else:
                    file_type = "file"

    if not prompt and not file_path:
        return jsonify({"status": "error", "message": "Введите сообщение или прикрепите файл"}), 400

    price = get_ai_price()

    # 1. Проверяем баланс и читаем последние 10 сообщений для контекста
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)
    try:
        cur.execute("SELECT balance FROM users WHERE id = %s", (session["user_id"],))
        row = cur.fetchone()
        if row is None:
            return jsonify({"status": "error", "message": "Пользователь не найден"}), 404
        if row["balance"] < price:
            return jsonify({
                "status": "error",
                "message": f"Недостаточно средств. Нужно {price} ₽, у вас {row['balance']} ₽"
            }), 402

        cur.execute(
            "SELECT role, content FROM chat_messages WHERE user_id = %s ORDER BY id DESC LIMIT 10",
            (session["user_id"],)
        )
        hist_rows = cur.fetchall()
        history = list(reversed(hist_rows)) if hist_rows else []
    finally:
        cur.close()
        cnx.close()

    # 2. Запрос к GigaChat API (выполняется БЕЗ открытых соединений с БД)
    try:
        answer = ask_gigachat(
            prompt=prompt,
            file_path=file_path,
            mime_type=mime_type,
            history=history
        )
    except ValueError as ve:
        return jsonify({"status": "error", "message": str(ve)}), 400
    except Exception as exc:
        return jsonify({"status": "error", "message": f"Ошибка нейросети: {exc}"}), 502

    # 3. Списываем средства, пишем транзакцию и сохраняем сообщения в чат
    now_str = datetime.now().strftime("%H:%M")
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)
    try:
        cur.execute(
            "UPDATE users SET balance = balance - %s WHERE id = %s AND balance >= %s",
            (price, session["user_id"], price)
        )
        cur.execute("SELECT balance FROM users WHERE id = %s", (session["user_id"],))
        res = cur.fetchone()
        new_balance = res["balance"] if res else row["balance"] - price

        tx_desc = "Запрос к нейросети"
        if file_type == "image":
            tx_desc = "Запрос к нейросети (фото)"
        elif file_type == "audio":
            tx_desc = "Запрос к нейросети (аудио)"

        cur.execute(
            "INSERT INTO transactions (user_id, amount, type, description, balance_after) "
            "VALUES (%s, %s, %s, %s, %s)",
            (session["user_id"], -price, "ai_request", tx_desc, new_balance)
        )

        cur.execute(
            "INSERT INTO chat_messages (user_id, role, content, file_url, file_type, file_name) "
            "VALUES (%s, 'user', %s, %s, %s, %s)",
            (session["user_id"], prompt, file_url, file_type, file_name)
        )
        user_msg_id = cur.lastrowid

        cur.execute(
            "INSERT INTO chat_messages (user_id, role, content) "
            "VALUES (%s, 'assistant', %s)",
            (session["user_id"], answer)
        )
        asst_msg_id = cur.lastrowid

        cnx.commit()
    finally:
        cur.close()
        cnx.close()

    return jsonify({
        "status": "ok",
        "answer": answer,
        "user_message": {
            "id": user_msg_id,
            "role": "user",
            "content": prompt,
            "file_url": file_url,
            "file_type": file_type,
            "file_name": file_name,
            "time": now_str
        },
        "assistant_message": {
            "id": asst_msg_id,
            "role": "assistant",
            "content": answer,
            "time": now_str
        },
        "balance": new_balance,
        "spent": price
    })


# ==========================================================
# ==============           АДМИНКА           ===============
# ==========================================================

@app.route("/admin")
@admin_required
def admin_page():
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)
    cur.execute(
        "SELECT id, username, surname, email, balance, is_admin, created_at "
        "FROM users ORDER BY id ASC"
    )
    users = cur.fetchall()

    cur.execute("SELECT COUNT(*) AS c FROM users")
    total_users = cur.fetchone()["c"]

    cur.execute("SELECT COALESCE(SUM(balance),0) AS s FROM users")
    total_balance = cur.fetchone()["s"]

    cur.execute("SELECT COUNT(*) AS c FROM users WHERE is_admin = 1")
    total_admins = cur.fetchone()["c"]

    cur.close(); cnx.close()

    return render_template(
        "admin.html",
        users=users,
        total_users=total_users,
        total_balance=total_balance,
        total_admins=total_admins,
        ai_price=get_ai_price(),   # ← NEW
    )

@app.route("/admin/settings/ai_price", methods=["POST"])
@admin_required
def admin_set_ai_price():
    data = request.get_json() or {}
    try:
        new_price = int(data.get("price"))
    except (TypeError, ValueError):
        return jsonify({"status": "error",
                        "message": "Цена должна быть целым числом"}), 400

    if new_price < 0:
        return jsonify({"status": "error",
                        "message": "Цена не может быть отрицательной"}), 400

    if new_price > 100000:
        return jsonify({"status": "error",
                        "message": "Слишком большая цена"}), 400

    set_ai_price(new_price)
    return jsonify({"status": "ok", "price": new_price})


@app.route("/admin/user/<int:user_id>/balance", methods=["POST"])
@admin_required
def admin_set_balance(user_id):
    data = request.get_json() or {}
    try:
        new_balance = int(data.get("balance"))
    except (TypeError, ValueError):
        return jsonify({"status": "error",
                        "message": "Баланс должен быть числом"}), 400

    cnx = get_db()
    cur = cnx.cursor()
    cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
    if not cur.fetchone():
        cur.close(); cnx.close()
        return jsonify({"status": "error",
                        "message": "Пользователь не найден"}), 404

    cur.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
    old_row = cur.fetchone()
    old_balance = old_row[0] if old_row else 0
    delta = new_balance - old_balance

    cur.execute("UPDATE users SET balance = %s WHERE id = %s", (new_balance, user_id))
    cur.execute(
        "INSERT INTO transactions (user_id, amount, type, description, balance_after) "
        "VALUES (%s, %s, %s, %s, %s)",
        (user_id, delta, "admin_adjustment", "Корректировка администратором", new_balance)
    )
    cnx.commit()
    cur.close(); cnx.close()

    return jsonify({"status": "ok", "balance": new_balance})


@app.route("/admin/user/<int:user_id>/toggle_admin", methods=["POST"])
@admin_required
def admin_toggle_admin(user_id):
    if user_id == session["user_id"]:
        return jsonify({"status": "error",
                        "message": "Нельзя снять права с самого себя"}), 400

    cnx = get_db()
    cur = cnx.cursor(dictionary=True)
    cur.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); cnx.close()
        return jsonify({"status": "error",
                        "message": "Пользователь не найден"}), 404

    new_flag = 0 if row["is_admin"] else 1
    cur.execute("UPDATE users SET is_admin = %s WHERE id = %s",
                (new_flag, user_id))
    cnx.commit()
    cur.close(); cnx.close()

    return jsonify({"status": "ok", "is_admin": new_flag})


@app.route("/admin/user/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    if user_id == session["user_id"]:
        return jsonify({"status": "error",
                        "message": "Нельзя удалить самого себя"}), 400

    cnx = get_db()
    cur = cnx.cursor()
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    cnx.commit()
    affected = cur.rowcount
    cur.close(); cnx.close()

    if affected == 0:
        return jsonify({"status": "error",
                        "message": "Пользователь не найден"}), 404

    return jsonify({"status": "ok"})


# ---------- 403 страница ----------
@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403


if __name__ == "__main__":
    app.run(debug=True)