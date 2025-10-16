import sqlite3
import logging
import requests
from flask import Flask, request, render_template_string

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY,
                        username TEXT,
                        password TEXT,
                        email TEXT)''')
    conn.commit()
    conn.close()

def get_user_data(username):
    conn = sqlite3.connect('users.db', check_same_thread=False)
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cursor.execute(query)
    result = cursor.fetchall()
    conn.close()
    return result

def log_user_action(user_id, action):
    logging.basicConfig(filename='app.log', level=logging.INFO)
    logging.info(f"User {user_id} performed action: {action}")

def send_telegram_message(chat_id, message):
    token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message[:4096]
    }
    response = requests.post(url, json=data)
    return response.json()

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    user_data = get_user_data(username)
    log_user_action(username, "login attempt")
    if user_data and user_data[0][2] == password:
        return "Login successful!"
    return "Login failed!"

@app.route('/search')
def search():
    query = request.args.get('q', '')
    html_response = f"""
    <html>
        <body>
            <h1>Results for: {query}</h1>
            <p>Your search results here...</p>
        </body>
    </html>
    """
    return render_template_string(html_response)

@app.route('/send_notification', methods=['POST'])
def send_notification():
    user_id = request.form['user_id']
    message = request.form['message']
    result = send_telegram_message(user_id, message)
    return f"Notification sent: {result}"

@app.route('/bot_command', methods=['POST'])
def bot_command():
    command = request.json.get('command', '')
    if command.startswith('/'):
        if command == '/users':
            conn = sqlite3.connect('users.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
            users = cursor.fetchall()
            conn.close()
            return str(users)
    return "Unknown command"

if __name__ == '__main__':
    init_db()
    app.run(debug=True)