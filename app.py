from flask import Flask, render_template, request, session, redirect, flash, send_from_directory
from utils.model_handler import get_response
from utils.session_manager import create_session, add_message, save_session
import os, json, csv
from datetime import datetime
import pandas as pd
from flask import jsonify
from flask_pymongo import PyMongo
from bson.objectid import ObjectId

app = Flask(__name__)
app.secret_key = "435664546465443466"


app.config["MONGO_URI"] = os.getenv("MONGO_URI")
mongo = PyMongo(app)

CONTEXT_FILE = "context.json"
TRACKING_FILE = "user_sessions.csv"
MODEL_COUNT = {"GPT-4_notfinetuned": 0, "LLaMA_notfinetuned": 0}

@app.before_request
def init_once():
    # Remove file system initialization if using MongoDB exclusively
    # os.makedirs("chats", exist_ok=True)
    # if not os.path.exists(TRACKING_FILE):
    #    with open(TRACKING_FILE, "w", newline="") as f:
    #         writer = csv.writer(f)
    #         writer.writerow(["prolific_id", "session_id", "model", "questions", "start_time", "end_time", "chat_duration"])
    session.setdefault("initialized", True)

# @app.route("/chat-log/<filename>")
# def serve_chat_log(filename):
#     return send_from_directory("chats", filename)

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
    
    sessions = list(mongo.db.chat_sessions.find())
    return render_template("admin_dashboard.html", sessions=sessions)

@app.route("/admin-stats")
def admin_stats():
    if session.get("role") != "admin":
        return redirect("/chat")
    
    records = list(mongo.db.chat_sessions.find())
    # Optionally add a flag if chat history exists
    for record in records:
        record["chat_exists"] = bool(record.get("chat_history"))
    return render_template("admin_stats.html", records=records)

from flask import send_file

@app.route("/export-excel")
def export_excel():
    if session.get("role") != "admin":
        return redirect("/chat")
    
    # Get all sessions without the MongoDB _id field if desired
    records = list(mongo.db.chat_sessions.find({}, {'_id': 0}))
    df = pd.DataFrame(records)
    output_path = "dashboard_export.xlsx"
    df.to_excel(output_path, index=False)
    return send_file(output_path, as_attachment=True)

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
    
    # If POST request is used
    if request.method == "POST":
        if "exit" in request.form:
            return redirect("/exit")
            
        # For admin session where model was pre-selected
        if session.get("role") == "admin" and "model" in request.form:
            model = request.form["model"]
            selected_context = context_data["gpt"] if model.startswith("GPT-4") else context_data["llama"]
            data = create_session(model, selected_context)
            data["prolific_id"] = "admin-session"
            data["questions"] = 0
            data["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data["end_time"] = ""
            data["chat_duration"] = ""
            data["chat_history"] = []  # initialize an empty chat history

            # Insert the session document into MongoDB
            result = mongo.db.chat_sessions.insert_one(data)
            session["chat_session_id"] = str(result.inserted_id)
            return redirect("/chat")
        
        # For regular POST messages, update chat history
        if "message" in request.form and "chat_session_id" in session:
            prompt = request.form.get("message")
            chat_session = mongo.db.chat_sessions.find_one({"_id": ObjectId(session["chat_session_id"])})
            history = chat_session.get("chat_history", [])
            reply = get_response(chat_session["model"], chat_session["context"], history, prompt)
            # Append the interaction to the chat history
            history.append({"user": prompt, "response": reply})
            # Update the document with new chat history and increased question count
            mongo.db.chat_sessions.update_one(
                {"_id": chat_session["_id"]},
                {"$set": {"chat_history": history},
                 "$inc": {"questions": 1}}
            )
    
    # If no chat session exists, create a new session document
    if "chat_session_id" not in session:
        # Decide model for non-admin users automatically
        # if session.get("role") != "admin":
        #     model = "GPT-4_notfinetuned" if MODEL_COUNT["GPT-4_notfinetuned"] <= MODEL_COUNT["LLaMA_notfinetuned"] else "LLaMA_notfinetuned"
        #     MODEL_COUNT[model] += 1
        #     selected_context = context_data["gpt"] if model.startswith("GPT-4") else (
        #         context_data["gpt"] if context_data.get("use_same") else context_data["llama"]
        #     )
        # else:
        #     # For admin default
        #     model = "GPT-4_notfinetuned"
        #     selected_context = context_data["gpt"]

        model = "GPT-4_notfinetuned" if MODEL_COUNT["GPT-4_notfinetuned"] <= MODEL_COUNT["LLaMA_notfinetuned"] else "LLaMA_notfinetuned"
        MODEL_COUNT[model] += 1
        selected_context = context_data["gpt"] if model.startswith("GPT-4") else (
            context_data["gpt"] if context_data.get("use_same") else context_data["llama"]
        )

        data = create_session(model, selected_context)
        data["prolific_id"] = session.get("prolific_id", "")
        data["questions"] = 0
        data["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data["end_time"] = ""
        data["chat_duration"] = ""
        data["chat_history"] = []

        result = mongo.db.chat_sessions.insert_one(data)
        session["chat_session_id"] = str(result.inserted_id)
    
    # Render the appropriate template based on the role
    chat_session = mongo.db.chat_sessions.find_one({"_id": ObjectId(session["chat_session_id"])})
    template = "chat_admin.html" if session.get("role") == "admin" else "chat.html"
    return render_template(template, session_data=chat_session)



@app.route("/chat-log/<session_identifier>")
def chat_log(session_identifier):
    # First try to find using the custom session_id field
    chat_session = mongo.db.chat_sessions.find_one({"session_id": session_identifier})
    
    # If not found, try using the MongoDB _id field
    if not chat_session:
        try:
            chat_session = mongo.db.chat_sessions.find_one({"_id": ObjectId(session_identifier)})
        except Exception:
            pass
    if not chat_session:
        return "Chat session not found", 404
    return jsonify(chat_history=chat_session.get("chat_history", []))



@app.route("/exit", methods=["POST"])
def exit_chat():
    if "chat_session_id" in session:
        chat_session = mongo.db.chat_sessions.find_one({"_id": ObjectId(session["chat_session_id"])})
        if chat_session:
            end_time = datetime.now()
            end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
            start_dt = datetime.strptime(chat_session["start_time"], "%Y-%m-%d %H:%M:%S")
            duration = end_time - start_dt
            minutes, seconds = divmod(duration.total_seconds(), 60)
            chat_duration = f"{int(minutes)} min {int(seconds)} sec"
            
            mongo.db.chat_sessions.update_one(
                {"_id": chat_session["_id"]},
                {"$set": {"end_time": end_time_str, "chat_duration": chat_duration}}
            )
    session.clear()
    return redirect("/")