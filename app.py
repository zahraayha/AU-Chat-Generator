import os
import uuid
from pathlib import Path
from datetime import date

from dotenv import load_dotenv
from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "local-dev-key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

UPLOAD_FOLDER = Path(os.getenv("UPLOAD_FOLDER", "uploads"))
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

db = SQLAlchemy(app)


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    character_name = db.Column(db.String(120), nullable=False)
    avatar_path = db.Column(db.String(500), nullable=True)
    conversation_date = db.Column(db.String(10), nullable=False)
    start_time = db.Column(db.String(5), nullable=False)
    delivered = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    messages = db.relationship(
        "Message", back_populates="conversation",
        cascade="all, delete-orphan", order_by="Message.position"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "character_name": self.character_name,
            "avatar_path": self.avatar_path,
            "conversation_date": self.conversation_date,
            "start_time": self.start_time,
            "delivered": self.delivered,
            "messages": [message.to_dict() for message in self.messages],
        }


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    sender = db.Column(db.String(10), nullable=False)
    message_type = db.Column(db.String(10), default="text", nullable=False)
    content = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(500), nullable=True)
    sent_at = db.Column(db.String(5), nullable=False)
    reaction = db.Column(db.String(20), nullable=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    conversation = db.relationship("Conversation", back_populates="messages")

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "sender": self.sender,
            "message_type": self.message_type,
            "content": self.content,
            "image_path": self.image_path,
            "sent_at": self.sent_at,
            "reaction": self.reaction,
            "position": self.position,
        }


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "message": "AU Chat Generator is running!",
        }), 200
    except Exception:
        db.session.rollback()
        app.logger.exception("Health check failed")
        return jsonify({"status": "unhealthy", "database": "disconnected"}), 503


@app.route("/api/uploads", methods=["POST"])
def upload_image():
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"success": False, "message": "Image file is required"}), 400

    extension = ALLOWED_IMAGES.get(uploaded.mimetype)
    if extension is None:
        return jsonify({"success": False, "message": "Only JPG, PNG, and WEBP are allowed"}), 400

    filename = f"{uuid.uuid4().hex}{extension}"
    uploaded.save(UPLOAD_FOLDER / filename)
    return jsonify({"success": True, "path": f"/uploads/{filename}"}), 201


@app.route("/uploads/<path:filename>", methods=["GET"])
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/api/conversations", methods=["GET"])
def get_conversations():
    conversations = Conversation.query.order_by(Conversation.id.asc()).all()
    return jsonify({
        "success": True,
        "count": len(conversations),
        "data": [conversation.to_dict() for conversation in conversations],
    }), 200


@app.route("/api/conversations/<int:conversation_id>", methods=["GET"])
def get_conversation(conversation_id):
    conversation = db.session.get(Conversation, conversation_id)
    if conversation is None:
        return jsonify({"success": False, "message": "Conversation not found"}), 404
    return jsonify({"success": True, "data": conversation.to_dict()}), 200


@app.route("/api/conversations", methods=["POST"])
def create_conversation():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "Invalid JSON data"}), 400

    character_name = data.get("character_name")
    if not isinstance(character_name, str) or not character_name.strip():
        return jsonify({"success": False, "message": "Character name is required"}), 400

    messages = data.get("messages", [])
    if not isinstance(messages, list):
        return jsonify({"success": False, "message": "Messages must be a list"}), 400

    conversation = Conversation(
        character_name=character_name.strip(),
        avatar_path=data.get("avatar_path"),
        conversation_date=data.get("conversation_date", date.today().isoformat()),
        start_time=data.get("start_time", "21:02"),
        delivered=bool(data.get("delivered", True)),
    )

    for index, message_data in enumerate(messages):
        if not isinstance(message_data, dict):
            return jsonify({"success": False, "message": "Each message must be an object"}), 400

        sender = message_data.get("sender")
        message_type = message_data.get("message_type", "text")
        content = message_data.get("content")
        image_path = message_data.get("image_path")

        if sender not in {"received", "sent"}:
            return jsonify({"success": False, "message": f"Invalid sender in message {index + 1}"}), 400
        if message_type not in {"text", "image"}:
            return jsonify({"success": False, "message": f"Invalid message type in message {index + 1}"}), 400
        if message_type == "text" and (not isinstance(content, str) or not content.strip()):
            return jsonify({"success": False, "message": f"Text message {index + 1} cannot be empty"}), 400
        if message_type == "image" and not image_path:
            return jsonify({"success": False, "message": f"Image message {index + 1} must be uploaded first"}), 400

        conversation.messages.append(Message(
            sender=sender,
            message_type=message_type,
            content=content,
            image_path=image_path,
            sent_at=message_data.get("sent_at", "21:02"),
            reaction=message_data.get("reaction"),
            position=index,
        ))

    try:
        db.session.add(conversation)
        db.session.commit()
        return jsonify({
            "success": True,
            "message": "Conversation saved to PostgreSQL",
            "data": conversation.to_dict(),
        }), 201
    except Exception:
        db.session.rollback()
        app.logger.exception("Failed to save conversation")
        return jsonify({"success": False, "message": "Failed to save conversation"}), 500


@app.route("/api/conversations/<int:conversation_id>", methods=["DELETE"])
def delete_conversation(conversation_id):
    conversation = db.session.get(Conversation, conversation_id)
    if conversation is None:
        return jsonify({"success": False, "message": "Conversation not found"}), 404
    try:
        db.session.delete(conversation)
        db.session.commit()
        return jsonify({"success": True, "message": "Conversation deleted"}), 200
    except Exception:
        db.session.rollback()
        app.logger.exception("Failed to delete conversation")
        return jsonify({"success": False, "message": "Failed to delete conversation"}), 500


with app.app_context():
    db.create_all()
    print("PostgreSQL tables are ready!")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
