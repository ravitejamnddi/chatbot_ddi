import uuid, json, os

CHAT_DIR = "chats"
os.makedirs(CHAT_DIR, exist_ok=True)

def create_session(model, context=""):
    return {
        "session_id": str(uuid.uuid4()),
        "model": model,
        "context": context,
        "chat_history": []
    }

def add_message(session_data, user, response):
    session_data["chat_history"].append({"user": user, "response": response})

def save_session(session_data):
    path = os.path.join(CHAT_DIR, f"chat_{session_data['session_id']}.json")
    with open(path, "w") as f:
        json.dump(session_data, f, indent=4)
    return path
