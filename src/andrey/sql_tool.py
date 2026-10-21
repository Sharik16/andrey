import mysql.connector

DB_CONFIG = {
    "host": "185.114.247.43",
    "port": 3306,
    "database": "sch688_vvedenie",
    "user": "sch688_vvedenie",
    "password": "Qwerty123",
}


def run_sql(sql, params=None, fetch=True):
    """Выполняет SQL. Если fetch=True — возвращает строки, иначе None."""
    cnx = mysql.connector.connect(**DB_CONFIG)
    cur = cnx.cursor(dictionary=True)
    cur.execute(sql, params or ())
    rows = cur.fetchall() if fetch else None
    cnx.commit()
    cur.close()
    cnx.close()
    return rows


def column_exists(table, column):
    """Проверяет, есть ли колонка в таблице."""
    rows = run_sql(
        "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (DB_CONFIG["database"], table, column)
    )
    return rows[0]["c"] > 0


def add_column_if_missing(table, column, definition):
    """Добавляет колонку, если её нет. Иначе — сообщает, что уже есть."""
    if column_exists(table, column):
        print(f"  ✔ Колонка `{column}` уже существует в `{table}` — пропускаю")
        return
    run_sql(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}",
            fetch=False)
    print(f"  ✔ Колонка `{column}` добавлена в `{table}`")


def show_users():
    print("\n=== Все пользователи ===")
    rows = run_sql(
        "SELECT id, username, surname, email, balance, is_admin "
        "FROM users ORDER BY id"
    )
    if not rows:
        print("  (пока никого)")
        return
    # Шапка
    print(f"  {'id':<4} {'имя':<15} {'фамилия':<15} "
          f"{'email':<28} {'баланс':>8} {'админ':>6}")
    print("  " + "-" * 80)
    for u in rows:
        print(f"  {u['id']:<4} {(u['username'] or ''):<15} "
              f"{(u['surname'] or '—'):<15} "
              f"{(u['email'] or ''):<28} "
              f"{u['balance']:>8} "
              f"{'да' if u['is_admin'] else 'нет':>6}")


def grant_admin(email):
    """Выдаёт админку по email."""
    rows = run_sql("SELECT id FROM users WHERE email = %s", (email,))
    if not rows:
        print(f"  ✖ Пользователь с email {email} не найден")
        return
    run_sql("UPDATE users SET is_admin = 1 WHERE email = %s",
            (email,), fetch=False)
    print(f"  ✔ {email} теперь админ")


def revoke_admin(email):
    """Снимает админку по email."""
    run_sql("UPDATE users SET is_admin = 0 WHERE email = %s",
            (email,), fetch=False)
    print(f"  ✔ {email} больше не админ")


# ============================================================
#  ГЛАВНЫЙ БЛОК — тут меняйте, что именно сделать
# ============================================================
if __name__ == "__main__":
    run_sql(
    "CREATE TABLE IF NOT EXISTS settings ("
    "  `key` VARCHAR(50) PRIMARY KEY,"
    "  `value` VARCHAR(255) NOT NULL"
    ")", fetch=False)
    # run_sql(
    # "INSERT INTO settings (`key`, `value`) VALUES ('ai_price', '3') "
    # "ON DUPLICATE KEY UPDATE `value` = `value`", fetch=False)
    # print("Таблица settings готова")

    print("=== Шаг 1. Проверяю / создаю колонку is_admin ===")
    add_column_if_missing("users", "is_admin",
                          "TINYINT(1) NOT NULL DEFAULT 0")

    print("\n=== Шаг 2. Текущее состояние пользователей ===")
    show_users()

    # --- Раскомментируйте нужное ниже ---

    print("\n=== Выдаю админку ===")
    grant_admin("1@111.ru")

    # print("\n=== Снимаю админку ===")
    # revoke_admin("admin@mail.ru")

    #print("\n=== Итоговое состояние ===")
    #show_users()