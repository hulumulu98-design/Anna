# database.py
import sqlite3
from datetime import datetime, timedelta
import os

def init_db():
    conn = sqlite3.connect('database.db')
    cur = conn.cursor()
    
    # Таблица пользователей
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        is_subscribed BOOLEAN DEFAULT FALSE,
        subscribed_until DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Таблица сообщений
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    """)
    
    conn.commit()
    conn.close()

# Функции для работы с пользователями
def get_user(user_id):
    conn = sqlite3.connect('database.db')
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cur.fetchone()
    conn.close()
    return user

def add_user(user_id, username, full_name):
    conn = sqlite3.connect('database.db')
    cur = conn.cursor()
    trial_end = datetime.now() + timedelta(days=1)
    try:
        cur.execute(
            "INSERT INTO users (user_id, username, full_name, is_subscribed, subscribed_until) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, full_name, True, trial_end.date())
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()

def check_subscription(user_id):
    conn = sqlite3.connect('database.db')
    cur = conn.cursor()
    cur.execute("SELECT is_subscribed, subscribed_until FROM users WHERE user_id = ?", (user_id,))
    result = cur.fetchone()
    conn.close()

    if not result:
        return False

    is_subscribed, subscribed_until = result
    if is_subscribed and subscribed_until and datetime.strptime(subscribed_until, '%Y-%m-%d').date() >= datetime.now().date():
        return True
    return False

# Функции для работы с сообщениями (ОБЯЗАТЕЛЬНЫЕ ФУНКЦИИ)
def add_message(user_id: int, role: str, content: str):
    """Добавляет сообщение в историю диалога."""
    conn = sqlite3.connect('database.db')
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content[:4000])
        )
        conn.commit()
    except Exception as e:
        print(f"Ошибка при добавлении сообщения: {e}")
    finally:
        conn.close()

def get_recent_messages(user_id: int, limit: int = 15):
    """Возвращает последние сообщения диалога для поддержания контекста."""
    conn = sqlite3.connect('database.db')
    cur = conn.cursor()
    
    cur.execute("""
        SELECT role, content 
        FROM messages 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT ?
    """, (user_id, limit))
    
    messages = cur.fetchall()
    conn.close()
    
    result = []
    for role, content in reversed(messages):
        result.append({"role": role, "content": content})
    return result

def clear_chat_history(user_id: int):
    """Очищает историю диалога для пользователя."""
    conn = sqlite3.connect('database.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_user_profile(user_id: int) -> dict:
    """Возвращает данные профиля пользователя для команды /profile."""
    conn = sqlite3.connect('database.db')
    cur = conn.cursor()
    
    cur.execute("""
        SELECT user_id, username, full_name, is_subscribed, subscribed_until, created_at
        FROM users 
        WHERE user_id = ?
    """, (user_id,))
    
    user_data = cur.fetchone()
    conn.close()
    
    if not user_data:
        return None
        
    user_id, username, full_name, is_subscribed, subscribed_until, created_at = user_data
    
    conn = sqlite3.connect('database.db')
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,))
    message_count = cur.fetchone()[0]
    conn.close()
    
    profile = {
        'user_id': user_id,
        'username': username,
        'full_name': full_name,
        'is_subscribed': bool(is_subscribed),
        'subscribed_until': subscribed_until,
        'created_at': created_at,
        'message_count': message_count
    }
    
    return profile

# Инициализируем БД при импорте
init_db()
