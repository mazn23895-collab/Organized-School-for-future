from fastapi import FastAPI, Form, File, UploadFile, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
import os, psycopg2, shutil, uuid, pandas as pd
from dotenv import load_dotenv
from datetime import date, datetime, timedelta

load_dotenv()
app = FastAPI(title="School Platform")

# ====== CONFIG ======
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey123")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
DATABASE_URL = os.getenv("DATABASE_URL")
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# ====== DB ======
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    try:
        yield conn, cur
    finally:
        cur.close()
        conn.close()

def hash_password(password): return pwd_context.hash(password)
def verify_password(password, hashed): return pwd_context.verify(password, hashed)
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# ====== UI ======
def header():
    return """<div style="background:white;padding:20px;text-align:center;border-bottom:4px solid #667eea;margin-bottom:20px;border-radius:15px;box-shadow:0 4px 12px rgba(0,0,0,0.1)">
<h1 style="margin:5px 0;color:#667eea;font-size:24px">🏫 School Platform</h1>
<div style="margin-top:10px;font-size:13px;color:#444">
<p style="margin:3px 0"><b>Created by:</b></p>
<p style="margin:2px 0">1. Mazen Mahmoud Ahmed Mohammed</p>
<p style="margin:2px 0">2. Adam Mohammed Salah</p>
</div>
</div>"""

def logout_button():
    return """<a href="/logout" style="float:left;background:#dc3545;color:white;padding:8px 15px;border-radius:8px;text-decoration:none;font-weight:bold">خروج</a>"""

# ====== STARTUP ======
@app.on_event("startup")
def create_tables():
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS classes (id SERIAL PRIMARY KEY, name VARCHAR UNIQUE, grade VARCHAR);
            CREATE TABLE IF NOT EXISTS subjects (id SERIAL PRIMARY KEY, name VARCHAR UNIQUE);
            CREATE TABLE IF NOT EXISTS pending_students (student_code VARCHAR PRIMARY KEY, name VARCHAR, grade VARCHAR, class_id INT REFERENCES classes(id));
            CREATE TABLE IF NOT EXISTS students (id SERIAL PRIMARY KEY, student_code VARCHAR UNIQUE, name VARCHAR, phone VARCHAR UNIQUE, password VARCHAR, class_id INT REFERENCES classes(id), grade VARCHAR, is_leader BOOLEAN DEFAULT FALSE);
            CREATE TABLE IF NOT EXISTS teachers (id SERIAL PRIMARY KEY, name VARCHAR, phone VARCHAR UNIQUE, password VARCHAR);
            CREATE TABLE IF NOT EXISTS teacher_assignments (id SERIAL PRIMARY KEY, teacher_id INT REFERENCES teachers(id), class_id INT REFERENCES classes(id), subject_id INT REFERENCES subjects(id), UNIQUE(teacher_id, class_id, subject_id));
            CREATE TABLE IF NOT EXISTS homeworks (id SERIAL PRIMARY KEY, subject_id INT REFERENCES subjects(id), class_id INT REFERENCES classes(id), content TEXT, due_date VARCHAR, file_path VARCHAR, created_at TIMESTAMP DEFAULT NOW());
            CREATE TABLE IF NOT EXISTS chat (id SERIAL PRIMARY KEY, sender_name VARCHAR, class_id INT REFERENCES classes(id), message TEXT, time TIMESTAMP DEFAULT NOW());
            CREATE TABLE IF NOT EXISTS attendance (id SERIAL PRIMARY KEY, class_id INT REFERENCES classes(id), student_id INT REFERENCES students(id), att_date DATE, status VARCHAR, taken_by VARCHAR, UNIQUE(class_id, student_id, att_date));
            """)
            cur.execute("INSERT INTO classes (name, grade) VALUES ('1A','الاول الاعدادي'), ('1B','الاول الاعدادي'), ('2A','الثاني الاعدادي') ON CONFLICT (name) DO NOTHING;")
            cur.execute("INSERT INTO subjects (name) VALUES ('عربي'), ('رياضيات'), ('علوم'), ('انجليزي'), ('دراسات') ON CONFLICT (name) DO NOTHING;")
            conn.commit()

# ====== AUTH ======
@app.get("/logout")
def logout():
    response = RedirectResponse("/")
    response.delete_cookie("access_token")
    return response

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Not authenticated")

# ====== PAGES ======
@app.get("/", response_class=HTMLResponse)
def home():
    return f"""<html dir="rtl"><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{{font-family:Tahoma;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}}.card{{background:white;padding:30px;border-radius:20px;width:90%;max-width:420px;box-shadow:0 10px 30px rgba(0,0,0,0.2)}}input,button,select{{width:100%;padding:12px;margin:8px 0;border-radius:10px;border:1px solid #ddd;box-sizing:border-box}}button{{background:#4CAF50;color:white;border:none;font-weight:bold;cursor:pointer}}a{{text-decoration:none}}</style></head>
    <body><div class="card">{header()}<h2 style="text-align:center">انشاء حساب جديد</h2>
    <form action="/register" method="post">
    <input name="name" placeholder="الاسم بالكامل كما في الشيت" required>
    <input name="student_code" placeholder="كود الطالب - اللي في وصل المصاريف">
    <input name="phone" placeholder="رقم التليفون" required>
    <input name="password" type="password" placeholder="كلمة السر" required>
    <select name="role" required><option value="">اختار نوع الحساب</option><option value="student">طالب</option><option value="teacher">مدرس</option></select>
    <button>تسجيل</button></form><a href="/login-page">عندي حساب بالفعل</a>
    <hr><a href="/upload-students">📤 رفع شيت الطلاب</a></div></body></html>"""

@app.post("/register")
def register(name=Form(...), student_code=Form(None), phone=Form(...), password=Form(...), role=Form(...)):
    hashed = hash_password(password)
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            try:
                if role == "student":
                    if not student_code: return HTMLResponse("كود الطالب مطلوب <a href='/'>رجوع</a>")
                    cur.execute("SELECT class_id, grade FROM pending_students WHERE student_code=%s AND name=%s", (student_code, name))
                    res = cur.fetchone()
                    if not res: return HTMLResponse("عذرا لم تنضم للفصل بعد <a href='/'>رجوع</a>")
                    class_id, grade = res
                    cur.execute("INSERT INTO students (student_code, name, phone, password, class_id, grade) VALUES (%s,%s,%s,%s,%s,%s)", (student_code, name, phone, hashed, class_id, grade))
                    cur.execute("DELETE FROM pending_students WHERE student_code=%s", (student_code,))
                else:
                    cur.execute("INSERT INTO teachers (name, phone, password) VALUES (%s,%s,%s)", (name, phone, hashed))
                conn.commit()
                return HTMLResponse("تم انشاء الحساب بنجاح <a href='/login-page'>سجل دخول</a>")
            except psycopg2.IntegrityError:
                return HTMLResponse("الرقم او كود الطالب مستخدم قبل كده <a href='/'>رجوع</a>")

@app.get("/login-page", response_class=HTMLResponse)
def login_page():
    return f"""<html dir="rtl"><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{{font-family:Tahoma;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}}.card{{background:white;padding:30px;border-radius:20px;width:90%;max-width:420px}}</style></head>
    <body><div class="card">{header()}<h2 style="text-align:center">🔑 تسجيل دخول</h2>
    <form action="/login" method="post"><input name="phone" placeholder="رقم التليفون" required><input name="password" type="password" placeholder="كلمة السر" required><button>دخول</button></form></div></body></html>"""

@app.post("/login")
def login(phone=Form(...), password=Form(...)):
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, password, class_id, grade FROM students WHERE phone=%s", (phone,))
            student = cur.fetchone()
            if student and verify_password(password, student[2]):
                token = create_access_token({"id": student[0], "name": student[1], "role": "student"})
                response = RedirectResponse(f"/student", 302)
                response.set_cookie("access_token", token)
                return response

            cur.execute("SELECT id, name, password FROM teachers WHERE phone=%s", (phone,))
            teacher = cur.fetchone()
            if teacher and verify_password(password, teacher[2]):
                token = create_access_token({"id": teacher[0], "name": teacher[1], "role": "teacher"})
                response = RedirectResponse(f"/teacher", 302)
                response.set_cookie("access_token", token)
                return response
    return HTMLResponse("رقم او باسورد غلط <a href='/login-page'>رجوع</a>")

# ====== STUDENT ======
@app.get("/student", response_class=HTMLResponse)
def student(user=Depends(get_current_user)):
    if user["role"]!= "student": return RedirectResponse("/login-page")
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT class_id, grade FROM students WHERE id=%s", (user["id"],))
            class_id, grade = cur.fetchone()
            if not class_id: return HTMLResponse(f"{header()}{logout_button()}<h2>عذرا لم تنضم للفصل بعد</h2>")
            cur.execute("SELECT name FROM classes WHERE id=%s", (class_id,))
            class_name = cur.fetchone()[0]
            cur.execute("SELECT h.content, s.name, h.due_date, h.file_path FROM homeworks h JOIN subjects s ON h.subject_id=s.id WHERE h.class_id=%s ORDER BY h.created_at DESC", (class_id,))
            hw = "".join([f"<div style='background:#f1f1f1;padding:12px;margin:8px 0;border-radius:8px'><b>{h[1]}</b><p>{h[0]}</p><small>التسليم: {h[2]}</small>{f'<br><a href=\"/{h[3]}\" target=\"_blank\">📎 تحميل</a>' if h[3] else ''}</div>" for h in cur.fetchall()])
            cur.execute("SELECT sender_name, message, time FROM chat WHERE class_id=%s ORDER BY time DESC LIMIT 30", (class_id,))
            chat = "".join([f"<p><b>{c[0]}:</b> {c[1]} <small>{c[2].strftime('%H:%M')}</small></p>" for c in cur.fetchall()])
            cur.execute("SELECT is_leader FROM students WHERE id=%s", (user["id"],))
            is_leader = cur.fetchone()[0]
            leader_btn = f"<a href='/take-attendance-page?class_id={class_id}' style='background:orange;color:white;padding:10px;border-radius:8px;display:block;text-align:center;margin-bottom:15px'>📝 اخذ الغياب</a>" if is_leader else ""
    return f"""<html dir="rtl"><body style="padding:20px;background:#f5f5f5;max-width:800px;margin:auto">
    {header()}{logout_button()}<h2>مرحبا {user['name']}</h2>
    <p style="background:#e7f3ff;padding:10px;border-radius:8px">الصف: {grade} | الفصل: {class_name}</p>
    {leader_btn}
    <div style="background:white;padding:15px;border-radius:10px;margin:15px 0"><h3>📚 الواجبات</h3>{hw or '<p>مفيش واجبات</p>'}</div>
    <div style="background:white;padding:15px;border-radius:10px"><h3>💬 شات الفصل</h3><div style="max-height:300px;overflow-y:auto">{chat}</div>
    <form action="/send-chat" method="post" style="display:flex;gap:5px;margin-top:10px">
    <input type="hidden" name="class_id" value="{class_id}">
    <input name="name" value="{user['name']}" type="hidden"><input name="msg" placeholder="اكتب رسالة" required style="flex:1;padding:10px"><button>ارسال</button></form></div></body></html>"""

@app.post("/send-chat")
def send_chat(class_id=Form(...), name=Form(...), msg=Form(...)):
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO chat (sender_name, class_id, message) VALUES (%s,%s,%s)", (name, class_id, msg))
            conn.commit()
    return RedirectResponse(f"/student", 302)

# ====== TEACHER ======
@app.get("/teacher", response_class=HTMLResponse)
def teacher(user=Depends(get_current_user)):
    if user["role"]!= "teacher": return RedirectResponse("/login-page")
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT c.name, s.name, c.id, s.id FROM teacher_assignments ta JOIN classes c ON ta.class_id=c.id JOIN subjects s ON ta.subject_id=s.id WHERE ta.teacher_id=%s", (user["id"],))
            assignments = cur.fetchall()
            if not assignments: return HTMLResponse(f"{header()}{logout_button()}<h2>عذرا لم يتم تعيينك بعد</h2>")
            assign_html = ""
            for a in assignments:
                class_name, subject_name, class_id, subject_id = a
                cur.execute("SELECT id, name FROM students WHERE class_id=%s", (class_id,))
                students = cur.fetchall()
                students_checkboxes = "".join([f"<label style='display:block'><input type='checkbox' name='student_{s[0]}' checked> {s[1]}</label>" for s in students])
                assign_html += f"""<div style="background:#d4edda;padding:15px;margin:10px 0;border-radius:10px">
                <h3>{subject_name} - فصل {class_name}</h3>
                <a href="/view-attendance?class_id={class_id}" style="background:blue;color:white;padding:8px 12px;border-radius:5px;text-decoration:none">📊 عرض الغياب</a>
                <hr>
                <form action="/add-homework" method="post" enctype="multipart/form-data">
                    <input type="hidden" name="class_id" value="{class_id}"><input type="hidden" name="subject_id" value="{subject_id}">
                    <textarea name="content" placeholder="محتوى الواجب" required style="width:100%;height:60px"></textarea>
                    <input name="due" type="date" required><input type="file" name="file"><button>نشر الواجب</button>
                </form>
                <hr><h4>📝 اخذ الغياب - {date.today()}</h4>
                <form action="/take-attendance" method="post">
                    <input type="hidden" name="class_id" value="{class_id}">{students_checkboxes}<button>حفظ الغياب</button>
                </form></div>"""
    return f"""<html dir="rtl"><body style="padding:20px;background:#f5f5f5;max-width:900px;margin:auto">
    {header()}{logout_button()}<h2>مرحبا مستر {user['name']}</h2>{assign_html}</body></html>"""

@app.post("/add-homework")
async def add_hw(class_id=Form(...), subject_id=Form(...), content=Form(...), due=Form(...), file: UploadFile = File(None)):
    file_path = None
    if file and file.filename:
        ext = file.filename.split('.')[-1]
        filename = f"{uuid.uuid4()}.{ext}"
        file_path = f"{UPLOAD_DIR}/{filename}"
        with open(file_path, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO homeworks (subject_id, class_id, content, due_date, file_path) VALUES (%s,%s,%s,%s,%s)", (subject_id, class_id, content, due, file_path))
            conn.commit()
    return HTMLResponse("تم نشر الواجب <a href='javascript:history.back()'>رجوع</a>")

@app.get("/view-attendance", response_class=HTMLResponse)
def view_attendance(class_id: int, user=Depends(get_current_user)):
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM classes WHERE id=%s", (class_id,))
            class_name = cur.fetchone()[0]
            cur.execute("SELECT s.name, a.att_date, a.status, a.taken_by FROM attendance a JOIN students s ON a.student_id=s.id WHERE a.class_id=%s ORDER BY a.att_date DESC", (class_id,))
            rows = cur.fetchall()
            table = "".join([f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td></tr>" for r in rows])
    return f"""<html dir="rtl"><body style="padding:20px">{header()}{logout_button()}<h2>سجل الغياب - فصل {class_name}</h2>
    <table border="1" style="width:100%;margin-top:15px;border-collapse:collapse"><tr><th>الاسم</th><th>التاريخ</th><th>الحالة</th><th>بواسطة</th></tr>{table}</table></body></html>"""

@app.post("/take-attendance")
async def take_attendance(request: Request):
    form = await request.form()
    class_id = int(form.get("class_id"))
    taken_by = "Teacher"
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            today = date.today()
            cur.execute("SELECT id FROM students WHERE class_id=%s", (class_id,))
            students = cur.fetchall()
            for s in students:
                status = "حاضر" if f"student_{s[0]}" in form else "غائب"
                cur.execute("INSERT INTO attendance (class_id, student_id, att_date, status, taken_by) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (class_id, student_id, att_date) DO UPDATE SET status=%s, taken_by=%s",
                            (class_id, s[0], today, status, taken_by, status, taken_by))
            conn.commit()
    return HTMLResponse("تم حفظ الغياب <a href='javascript:history.back()'>رجوع</a>")

@app.get("/take-attendance-page", response_class=HTMLResponse)
def take_attendance_page(class_id: int, user=Depends(get_current_user)):
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM students WHERE class_id=%s", (class_id,))
            students = cur.fetchall()
            students_checkboxes = "".join([f"<label style='display:block'><input type='checkbox' name='student_{s[0]}' checked> {s[1]}</label>" for s in students])
    return f"""<html dir="rtl"><body style="padding:20px">{header()}{logout_button()}<h2>اخذ الغياب - امين الفصل</h2>
    <form action="/take-attendance" method="post">
        <input type="hidden" name="class_id" value="{class_id}">
        {students_checkboxes}<button>حفظ الغياب</button>
    </form></body></html>"""

# ====== UPLOAD STUDENTS EXCEL ======
@app.get("/upload-students", response_class=HTMLResponse)
def upload_page():
    return f"""<html dir="rtl"><body style="padding:20px">{header()}{logout_button()}
    <h2>رفع شيت الطلاب</h2><p>الشيت لازم فيه الاعمدة: name, student_code, grade, class_name</p>
    <form action="/upload-students" method="post" enctype="multipart/form-data">
    <input type="file" name="file" accept=".xlsx" required><button>رفع</button></form></body></html>"""

@app.post("/upload-students")
async def upload_students(file: UploadFile = File(...)):
    df = pd.read_excel(file.file)
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for _, row in df.iterrows():
                cur.execute("SELECT id FROM classes WHERE name=%s", (row["class_name"],))
                res = cur.fetchone()
                if res: class_id = res[0]
                else:
                    cur.execute("INSERT INTO classes (name, grade) VALUES (%s,%s) RETURNING id", (row["class_name"], row["grade"]))
                    class_id = cur.fetchone()[0]
                cur.execute("INSERT INTO pending_students (student_code, name, grade, class_id) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (row["student_code"], row["name"], row["grade"], class_id))
            conn.commit()
    return HTMLResponse("تم رفع الطلاب بنجاح <a href='/'>رجوع</a>")
