from datetime import datetime
import base64
import os
import re
from flask import Flask, redirect, render_template, request, send_from_directory, url_for
import sqlite3

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def init_db():
    conn = sqlite3.connect("work_log.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS authors (
                    email TEXT PRIMARY KEY,
                    display_name TEXT,
                    department TEXT,
                    avatar_url TEXT
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS manuals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    email TEXT,
                    title TEXT,
                    category TEXT,
                    file_url TEXT,
                    content TEXT,
                    note TEXT,
                    ref_link TEXT
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                )""")
    
    # デフォルトのカテゴリーを初期登録
    default_cats = ["研修", "便利ツール", "メモ", "パス", "プログラム"]
    for cat in default_cats:
        c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))

    conn.commit()
    conn.close()

init_db()

def save_pasted_image(base64_str):
    if not base64_str or not base64_str.startswith("data:image"):
        return None
    try:
        format_match = re.match(r"data:image/(\w+);base64,", base64_str)
        ext = format_match.group(1) if format_match else "png"
        img_data = base64.b64decode(re.sub(r"^data:image/\w+;base64,", "", base64_str))
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_pasted.{ext}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        with open(filepath, "wb") as f:
            f.write(img_data)
        return filename
    except Exception as e:
        print("Image save error:", e)
        return None

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/")
def index():
    search = request.args.get("search", "")
    author_filter = request.args.get("author", "")
    category_filter = request.args.get("category", "").strip()

    conn = sqlite3.connect("work_log.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM authors")
    authors = c.fetchall()

    c.execute("SELECT name FROM categories ORDER BY id ASC")
    categories = [row["name"] for row in c.fetchall()]

    query = """
        SELECT m.*, a.display_name, a.department, a.avatar_url 
        FROM manuals m 
        LEFT JOIN authors a ON m.email = a.email 
        WHERE 1=1
    """
    params = []
    if search:
        query += " AND (m.title LIKE ? OR m.content LIKE ? OR a.display_name LIKE ? OR m.category LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
    if author_filter:
        query += " AND m.email = ?"
        params.append(author_filter)
    if category_filter:
        query += " AND (',' || REPLACE(m.category, ' ', '') || ',') LIKE ?"
        params.append(f"%,{category_filter},%")
        
    query += " ORDER BY m.id DESC"

    c.execute(query, params)
    manuals = c.fetchall()
    conn.close()

    return render_template(
        "index.html", 
        manuals=manuals, 
        authors=authors, 
        categories=categories,
        search=search, 
        selected_author=author_filter,
        selected_category=category_filter
    )

@app.route("/add_author", methods=["POST"])
def add_author():
    email = request.form.get("email", "").strip().lower()
    name = request.form.get("display_name", "").strip()
    dept = request.form.get("department", "").strip()
    avatar = request.form.get("avatar_url", "").strip()
    if email and name:
        conn = sqlite3.connect("work_log.db")
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO authors (email, display_name, department, avatar_url) VALUES (?, ?, ?, ?)",
                  (email, name, dept, avatar))
        conn.commit()
        conn.close()
    return redirect(url_for("index"))

@app.route("/add_category", methods=["POST"])
def add_category():
    new_cat = request.form.get("new_category", "").strip()
    if new_cat:
        conn = sqlite3.connect("work_log.db")
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (new_cat,))
        conn.commit()
        conn.close()
    return redirect(url_for("index"))

@app.route("/add_manual", methods=["POST"])
def add_manual():
    email = request.form.get("email")
    title = request.form.get("title")
    selected_cats = request.form.getlist("categories")
    category = ", ".join(selected_cats)
    content = request.form.get("content")
    ref_link = request.form.get("ref_link", "")
    pasted_img_data = request.form.get("pasted_image", "")

    saved_filenames = []
    if pasted_img_data:
        filename = save_pasted_image(pasted_img_data)
        if filename:
            saved_filenames.append(filename)

    files = request.files.getlist("images")
    for file in files:
        if file and file.filename:
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)
            saved_filenames.append(filename)

    file_url = ",".join(saved_filenames)
    timestamp = datetime.now().strftime("%Y/%m/%d %H:%M")

    if email and title and content:
        conn = sqlite3.connect("work_log.db")
        c = conn.cursor()
        c.execute("INSERT INTO manuals (timestamp, email, title, category, file_url, content, note, ref_link) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (timestamp, email, title, category, file_url, content, "", ref_link))
        conn.commit()
        conn.close()

    return redirect(url_for("index"))

@app.route("/edit_manual/<int:manual_id>", methods=["POST"])
def edit_manual(manual_id):
    title = request.form.get("title")
    selected_cats = request.form.getlist("categories")
    category = ", ".join(selected_cats)
    content = request.form.get("content")
    ref_link = request.form.get("ref_link", "")

    conn = sqlite3.connect("work_log.db")
    c = conn.cursor()
    c.execute("UPDATE manuals SET title = ?, category = ?, content = ?, ref_link = ? WHERE id = ?",
              (title, category, content, ref_link, manual_id))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/delete_manual/<int:manual_id>", methods=["POST"])
def delete_manual(manual_id):
    conn = sqlite3.connect("work_log.db")
    c = conn.cursor()
    c.execute("DELETE FROM manuals WHERE id = ?", (manual_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True, port=5000)