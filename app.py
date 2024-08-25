from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, g
from openai import OpenAI
from dotenv import load_dotenv
import os
import sqlite3
from datetime import datetime
import tempfile
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import traceback

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# .env 파일에서 환경 변수 로드
load_dotenv()

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# 데이터베이스 연결
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect('translations.db')
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'db'):
        g.db.close()

# 데이터베이스 초기화
def init_db():
    db = get_db()
    db.executescript('''
        DROP TABLE IF EXISTS users;
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );

        DROP TABLE IF EXISTS translations;
        CREATE TABLE translations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            source_text TEXT,
            translated_text TEXT,
            source_language TEXT,
            target_language TEXT,
            interpretation TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_user_id ON translations (user_id);
    ''')
    db.commit()

# 앱 시작 시 데이터베이스 초기화
with app.app_context():
    init_db()

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)
        
        db = get_db()
        try:
            db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            db.commit()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return "Username already exists"
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            return redirect(url_for('index'))
        return "Invalid username or password"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/translate', methods=['POST'])
def translate():
    if 'user_id' not in session:
        return jsonify({'error': 'User not authenticated'}), 401
    
    try:
        data = request.json
        text = data['text']
        source_language = data['source_language']
        target_language = data['target_language']

        # 번역
        translation_response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"You are a translator. Translate the given text from {source_language} to {target_language}. Provide only the direct translation without any additional text or punctuation."},
                {"role": "user", "content": text}
            ]
        )
        translation = translation_response.choices[0].message.content.strip()

        # 뉘앙스 해석
        if source_language == '한국어':
            interpretation_prompt = f"다음 영어 문장의 뉘앙스를 한국어로 설명해주세요: '{translation}'"
        else:
            interpretation_prompt = f"다음 영어 문장의 뉘앙스를 한국어로 설명해주세요: '{text}'"

        interpretation_response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "당신은 영어 문장의 뉘앙스를 한국어로 설명하는 전문가입니다."},
                {"role": "user", "content": interpretation_prompt}
            ]
        )
        interpretation = interpretation_response.choices[0].message.content.strip()

        # 데이터베이스에 저장
        db = get_db()
        db.execute("INSERT INTO translations (user_id, source_text, translated_text, source_language, target_language, interpretation, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (session['user_id'], text, translation, source_language, target_language, interpretation, datetime.now()))
        db.commit()

        return jsonify({
            'translation': translation,
            'interpretation': interpretation
        })
    except Exception as e:
        error_message = f"An error occurred during translation: {str(e)}"
        error_traceback = traceback.format_exc()
        app.logger.error(f"{error_message}\n{error_traceback}")
        return jsonify({'error': '번역 중 오류가 발생했습니다.'}), 500

@app.route('/get_translations', methods=['GET'])
def get_translations():
    if 'user_id' not in session:
        return jsonify({'error': 'User not authenticated'}), 401
    
    try:
        db = get_db()
        translations = db.execute("SELECT id, source_text, translated_text, source_language, target_language, interpretation, strftime('%Y-%m-%d', created_at) as date FROM translations WHERE user_id = ? ORDER BY created_at DESC", (session['user_id'],)).fetchall()

        translations_by_date = {}
        for t in translations:
            date = t['date']
            if date not in translations_by_date:
                translations_by_date[date] = []
            translations_by_date[date].append({
                'id': t['id'],
                'source_text': t['source_text'],
                'translated_text': t['translated_text'],
                'source_language': t['source_language'],
                'target_language': t['target_language'],
                'interpretation': t['interpretation']
            })

        return jsonify({'translations': translations_by_date})
    except Exception as e:
        error_message = f"An error occurred while fetching translations: {str(e)}"
        error_traceback = traceback.format_exc()
        app.logger.error(f"{error_message}\n{error_traceback}")
        return jsonify({'error': '번역 기록을 가져오는 중 오류가 발생했습니다.'}), 500

@app.route('/delete_translation/<int:id>', methods=['DELETE'])
def delete_translation(id):
    if 'user_id' not in session:
        return jsonify({'error': 'User not authenticated'}), 401
    
    try:
        db = get_db()
        db.execute("DELETE FROM translations WHERE id = ? AND user_id = ?", (id, session['user_id']))
        db.commit()
        return jsonify({'message': '번역 기록이 삭제되었습니다.'}), 200
    except Exception as e:
        error_message = f"An error occurred while deleting translation: {str(e)}"
        error_traceback = traceback.format_exc()
        app.logger.error(f"{error_message}\n{error_traceback}")
        return jsonify({'error': '번역 기록 삭제 중 오류가 발생했습니다.'}), 500

@app.route('/export_db', methods=['GET'])
def export_db():
    if 'user_id' not in session:
        return jsonify({'error': 'User not authenticated'}), 401
    
    temp_file_path = None
    try:
        # 임시 파일 생성
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file_path = temp_file.name
        temp_file.close()

        # 사용자의 번역 기록만 새 데이터베이스로 복사
        src_db = get_db()
        dst_db = sqlite3.connect(temp_file_path)
        
        dst_db.execute('''CREATE TABLE translations
                          (id INTEGER PRIMARY KEY AUTOINCREMENT,
                           source_text TEXT,
                           translated_text TEXT,
                           source_language TEXT,
                           target_language TEXT,
                           interpretation TEXT,
                           created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        # 사용자의 번역 기록 복사
        translations = src_db.execute("SELECT source_text, translated_text, source_language, target_language, interpretation, created_at FROM translations WHERE user_id = ?", (session['user_id'],)).fetchall()
        dst_db.executemany("INSERT INTO translations (source_text, translated_text, source_language, target_language, interpretation, created_at) VALUES (?, ?, ?, ?, ?, ?)", translations)

        dst_db.commit()
        dst_db.close()

        return send_file(
            temp_file_path,
            as_attachment=True,
            download_name='translations_backup.db',
            mimetype='application/x-sqlite3'
        )
    except Exception as e:
        error_message = f"데이터베이스 추출 중 오류 발생: {str(e)}"
        error_traceback = traceback.format_exc()
        app.logger.error(f"{error_message}\n{error_traceback}")
        return jsonify({'error': '데이터베이스 추출 중 오류가 발생했습니다.'}), 500
    finally:
        # 임시 파일 삭제
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as e:
                app.logger.error(f"임시 파일 삭제 중 오류 발생: {str(e)}")

if __name__ == '__main__':
    app.run(debug=True)
