from flask import Flask, render_template, request, session, redirect, flash, send_from_directory
from utils.model_handler import get_response
from utils.session_manager import create_session, add_message, save_session
import os, json, csv
from datetime import datetime
import pandas as pd

app = Flask(__name__)
app.secret_key = "435664546465443466"

CONTEXT_FILE = "context.json"
TRACKING_FILE = "user_sessions.csv"
MODEL_COUNT = {"GPT-4_notfinetuned": 0, "LLaMA_notfinetuned": 0}

@app.before_request
def init_once():
    if not session.get("initialized"):
        os.makedirs("chats", exist_ok=True)
        if not os.path.exists(TRACKING_FILE):
            with open(TRACKING_FILE, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["prolific_id", "session_id", "model", "questions", "start_time", "end_time", "chat_duration"])
        session["initialized"] = True

@app.route("/chat-log/<filename>")
def serve_chat_log(filename):
    return send_from_directory("chats", filename)

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form["role"]
        if role == "admin":
            if request.form.get("password") != "admin#1234":
                flash("Invalid admin password.")
                return redirect("/")
            session["username"] = request.form["username"]
            session["role"] = role
            return redirect("/admin-dashboard")
        else:
            session["prolific_id"] = request.form["prolific_id"]
            session["role"] = role
            return redirect("/chat")
    return render_template("login.html")

@app.route("/admin-dashboard")
def admin_dashboard():
    if session.get("role") != "admin":
        return redirect("/chat")

    prolific_ids = []
    if os.path.exists(TRACKING_FILE):
        with open(TRACKING_FILE, newline="") as f:
            reader = csv.DictReader(f)
            prolific_ids = list(reader)

    return render_template("admin_dashboard.html", prolific_ids=prolific_ids)

@app.route("/admin-stats")
def admin_stats():
    if session.get("role") != "admin":
        return redirect("/chat")

    records = []
    if os.path.exists(TRACKING_FILE):
        with open(TRACKING_FILE, newline="") as f:
            reader = csv.DictReader(f)
            records = list(reader)
    for row in records:
        chat_file = f"chats/chat_{row['session_id']}.json"
        row["chat_exists"] = os.path.exists(chat_file)
    return render_template("admin_stats.html", records=records)

@app.route("/export-excel")
def export_excel():
    if session.get("role") != "admin":
        return redirect("/chat")
    df = pd.read_csv(TRACKING_FILE)
    output_path = os.path.join("chats", "dashboard_export.xlsx")
    df.to_excel(output_path, index=False)
    return send_from_directory("chats", "dashboard_export.xlsx", as_attachment=True)

@app.route("/config", methods=["GET", "POST"])
def config():
    if session.get("role") != "admin":
        return redirect("/chat")
    context = {"use_same": True, "gpt": "", "llama": ""}
    if os.path.exists(CONTEXT_FILE):
        with open(CONTEXT_FILE) as f:
            context = json.load(f)
    if request.method == "POST":
        context["use_same"] = "use_same" in request.form
        context["gpt"] = request.form.get("context_gpt", "")
        context["llama"] = request.form.get("context_llama", "")
        with open(CONTEXT_FILE, "w") as f:
            json.dump(context, f)
        flash("Contexts updated successfully.")
        return redirect("/config")
    return render_template("config.html", context=context)

@app.route("/chat", methods=["GET", "POST"])
def chat():
    context_data = {"use_same": True, "gpt": "", "llama": ""}
    if os.path.exists(CONTEXT_FILE):
        with open(CONTEXT_FILE) as f:
            context_data = json.load(f)
    
    if request.method == "POST":
        if "exit" in request.form:
            return exit_chat()

        if session.get("role") == "admin" and "model" in request.form:
            model = request.form["model"]
            selected_context = context_data["gpt"] if model.startswith("GPT-4") else context_data["llama"]

            data = create_session(model, selected_context)
            data["prolific_id"] = "admin-session"
            data["questions"] = 0
            data["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data["end_time"] = ""
            data["chat_duration"] = ""
            session["session_data"] = data

            # ✅ Now after creating admin session, immediately reload chat page
            return redirect("/chat")


        # if admin is chatting normally (already selected model)
        if "message" in request.form:
            prompt = request.form.get("message")
            data = session["session_data"]
            reply = get_response(data["model"], data["context"], data["chat_history"], prompt)
            add_message(data, prompt, reply)
            data["questions"] += 1
            save_session(data)
            session["session_data"] = data

    # ✅ Now for both admin and user, check if session exists
    if "session_data" not in session:
        # No session created yet (first time user login)
        # if session.get("role") == "admin":
            # return render_template("chat_admin.html", context=context_data)

        # Normal user - assign model automatically
        if MODEL_COUNT["GPT-4_notfinetuned"] <= MODEL_COUNT["LLaMA_notfinetuned"]:
            model = "GPT-4_notfinetuned"
        else:
            model = "LLaMA_notfinetuned"
        MODEL_COUNT[model] += 1

        selected_context = context_data["gpt"] if model.startswith("GPT-4") else (
            context_data["gpt"] if context_data.get("use_same") else context_data["llama"]
        )

        data = create_session(model, selected_context)
        if session.get('role')=='admin' and session.get("prolific_id") is None:
            data["prolific_id"] = ''
        else:
            data["prolific_id"] = session["prolific_id"]
        data["questions"] = 0
        data["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data["end_time"] = ""
        data["chat_duration"] = ""
        session["session_data"] = data

        with open(TRACKING_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                data["prolific_id"], data["session_id"], data["model"],
                0, data["start_time"], "", ""
            ])

    # Finally render correct chat template based on role
    template = "chat_admin.html" if session.get("role") == "admin" else "chat.html"
    return render_template(template, session_data=session.get("session_data"))

@app.route("/exit", methods=["POST"])
def exit_chat():
    data = session.get("session_data")
    if data:
        end_time = datetime.now()
        data["end_time"] = end_time.strftime("%Y-%m-%d %H:%M:%S")

        start_dt = datetime.strptime(data["start_time"], "%Y-%m-%d %H:%M:%S")
        duration = end_time - start_dt
        minutes, seconds = divmod(duration.total_seconds(), 60)
        data["chat_duration"] = f"{int(minutes)} min {int(seconds)} sec"

        save_session(data)

        # ✅ Update CSV also
        rows = []
        if os.path.exists(TRACKING_FILE):
            with open(TRACKING_FILE, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["session_id"] == data["session_id"]:
                        row["end_time"] = data["end_time"]
                        row["chat_duration"] = data["chat_duration"]
                        row["questions"] = str(data["questions"])  # ✅ Now also update Questions!
                    rows.append(row)

        with open(TRACKING_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["prolific_id", "session_id", "model", "questions", "start_time", "end_time", "chat_duration"])
            writer.writeheader()
            writer.writerows(rows)

    session.clear()
    return redirect("/")
