# app.py
import os
from datetime import datetime, time
from enum import Enum
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from sqlalchemy import Enum as SQLEnum

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL", "sqlite:///./app.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class UserRole(Enum):
    ADMIN = "admin"
    DEVELOPER = "developer"
    CUSTOMER = "customer"

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.Integer, unique=True)
    display_name = db.Column(db.String(200))
    timezone = db.Column(db.String(100), nullable=True)
    working_hours_start = db.Column(db.Time, nullable=True)
    working_hours_end = db.Column(db.Time, nullable=True)
    role = db.Column(SQLEnum(UserRole), default=UserRole.CUSTOMER)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'telegram_id': self.telegram_id,
            'display_name': self.display_name,
            'timezone': self.timezone,
            'working_hours_start': str(self.working_hours_start),
            'working_hours_end': str(self.working_hours_end),
            'role': self.role.value,
            'created_at': str(self.created_at)
        }

class ChatRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer)
    name = db.Column(db.String(200))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('chat_room.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    content = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'room_id': self.room_id,
            'user_id': self.user_id,
            'content': self.content,
            'timestamp': str(self.timestamp)
        }

with app.app_context():
    db.create_all()

@app.route('/api/users', methods=['POST'])
def create_or_update_user():
    data = request.get_json()
    telegram_id = data.get('telegram_id')
    display_name = data.get('display_name')
    timezone = data.get('timezone')
    working_hours_start = data.get('working_hours_start')
    working_hours_end = data.get('working_hours_end')
    role = data.get('role')

    if not telegram_id or not display_name:
        return jsonify({'message': 'Missing required fields'}), 400

    user = User.query.filter_by(telegram_id=telegram_id).first()

    if user:
        user.display_name = display_name or user.display_name
        user.timezone = timezone or user.timezone
        if working_hours_start:
            user.working_hours_start = datetime.strptime(working_hours_start, '%H:%M').time()
        if working_hours_end:
            user.working_hours_end = datetime.strptime(working_hours_end, '%H:%M').time()
        if role:
            user.role = UserRole[role.upper()]
        db.session.commit()
        return jsonify(user.to_dict()), 200
    else:
        try:
            new_user = User(
                telegram_id=telegram_id,
                display_name=display_name,
                timezone=timezone,
                working_hours_start=datetime.strptime(working_hours_start, '%H:%M').time() if working_hours_start else None,
                working_hours_end=datetime.strptime(working_hours_end, '%H:%M').time() if working_hours_end else None,
                role=UserRole[role.upper()] if role else UserRole.CUSTOMER
            )
            db.session.add(new_user)
            db.session.commit()
            return jsonify(new_user.to_dict()), 201
        except (ValueError, KeyError) as e:
            return jsonify({'message': str(e)}), 400

@app.route('/api/users/<int:telegram_id>', methods=['GET'])
def get_user(telegram_id):
    user = User.query.filter_by(telegram_id=telegram_id).first()
    return jsonify(user.to_dict()), 200 if user else jsonify({'message': 'User not found'}), 404

@app.route('/api/users', methods=['GET'])
def list_users():
    users = User.query.all()
    return jsonify([user.to_dict() for user in users]), 200

@app.route('/api/rooms', methods=['POST'])
def create_room():
    data = request.get_json()
    creator_id = data.get('creator_id')
    name = data.get('name')

    if not creator_id or not name:
        return jsonify({'message': 'Missing required fields'}), 400

    new_room = ChatRoom(creator_id=creator_id, name=name)
    db.session.add(new_room)
    db.session.commit()
    return jsonify({'id': new_room.id, 'creator_id': new_room.creator_id, 'name': new_room.name}), 201

@app.route('/api/rooms', methods=['GET'])
def list_rooms():
    rooms = ChatRoom.query.all()
    return jsonify([{'id': room.id, 'creator_id': room.creator_id, 'name': room.name} for room in rooms]), 200

@app.route('/api/rooms/<int:room_id>/messages', methods=['GET'])
def get_room_messages(room_id):
    messages = Message.query.filter_by(room_id=room_id).all()
    return jsonify([message.to_dict() for message in messages]), 200

@app.route('/api/rooms/<int:room_id>/messages', methods=['POST'])
def send_message(room_id):
    data = request.get_json()
    user_id = data.get('user_id')
    content = data.get('content')

    if not user_id or not content:
        return jsonify({'message': 'Missing required fields'}), 400

    new_message = Message(room_id=room_id, user_id=user_id, content=content)
    db.session.add(new_message)
    db.session.commit()
    return jsonify(new_message.to_dict()), 201

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(debug=True, host="0.0.0.0", port=port)