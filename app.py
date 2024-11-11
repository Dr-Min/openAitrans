import os
import secrets
import sqlite3
import tempfile
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from flask import Flask, g, jsonify, redirect, render_template, request, send_file, session, url_for
from openai import OpenAI
from werkzeug.security import check_password_hash, generate_password_hash
from concurrent.futures import ThreadPoolExecutor, as_completed


app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# .env 파일에서 환경 변수 로드
load_dotenv()

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# 스레드 풀 생성
executor = ThreadPoolExecutor(max_workers=5)

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
    cursor = db.cursor()
    try:
        # users 테이블 생성
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')

        # translations 테이블 생성
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS translations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                source_text TEXT,
                translated_text TEXT,
                source_language TEXT,
                target_language TEXT,
                interpretation TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON translations (user_id)')
        
        db.commit()
        app.logger.info("Database initialized successfully.")
    except sqlite3.Error as e:
        app.logger.error(f"Database initialization error: {e}")
        db.rollback()

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

def save_translation(user_id, source_text, translated_text, source_language, target_language, interpretation):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO translations (user_id, source_text, translated_text, source_language, target_language, interpretation, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (user_id, source_text, translated_text, source_language, target_language, interpretation, datetime.now()))
        db.commit()

def translate_text(text, source_language, target_language):
    start_time = datetime.now()
    translation_prompt = f"Translate the following {source_language} text to {target_language}, providing a natural and accurate translation that captures the nuance and context: '{text}'"
    
    translation_response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a professional translator specializing in nuanced and contextually accurate translations.(번역 결과에 따옴표를 넣지 마세요 예를 들어 'hello'가 아닌 hello로 출력합니다)"},
            {"role": "user", "content": translation_prompt}
        ]
    )
    end_time = datetime.now()
    elapsed_time = (end_time - start_time).total_seconds()
    
    result = translation_response.choices[0].message.content.strip()
    return result, elapsed_time

def interpret_text(text, source_language, target_language):
    start_time = datetime.now()
    
    if source_language == "영어":
        interpretation_prompt = f"다음 영어 원문의 뉘앙스와 의미를 한국어로 자세히 설명해주세요. 왜 해당문장을 다음과 번역했는지도 설명해주세요: '{text}'"
        system_content = "당신은 영어 표현의 뉘앙스를 한국어로 설명하는 전문가입니다."
    else:
        interpretation_prompt = f"다음 영어 번역문의 뉘앙스와 의미를 한국어로 자세히 설명해주세요 왜 해당문장을 다음과 번역했는지도 설명해주세요: '{text}'"
        system_content = "당신은 영어 표현의 뉘앙스를 한국어로 설명하는 전문가입니다."

    interpretation_response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": interpretation_prompt}
        ]
    )
    
    end_time = datetime.now()
    elapsed_time = (end_time - start_time).total_seconds()
    
    result = interpretation_response.choices[0].message.content.strip()
    return result, elapsed_time

@app.route('/translate', methods=['POST'])
def translate():
    total_start_time = datetime.now()
    
    if 'user_id' not in session:
        return jsonify({'error': 'User not authenticated'}), 401
    
    data = request.json
    text = data['text']
    source_language = data['source_language']
    target_language = data['target_language']

    app.logger.info(f"Starting translation request: {text[:100]}...")
    
    translation_time = 0
    interpretation_time = 0
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        try:
            translation_future = executor.submit(translate_text, text, source_language, target_language)
            
            if source_language == "영어":
                interpretation_future = executor.submit(interpret_text, text, source_language, target_language)
                translation, translation_time = translation_future.result()
            else:
                translation, translation_time = translation_future.result()
                interpretation_future = executor.submit(interpret_text, translation, source_language, target_language)
            
            interpretation, interpretation_time = interpretation_future.result()
            
            save_start_time = datetime.now()
            save_translation(session['user_id'], text, translation, source_language, target_language, interpretation)
            save_time = (datetime.now() - save_start_time).total_seconds()
            
            total_time = (datetime.now() - total_start_time).total_seconds()
            
            return jsonify({
                'translation': translation,
                'interpretation': interpretation,
                'timing': {
                    'translation_time': translation_time,
                    'interpretation_time': interpretation_time,
                    'save_time': save_time,
                    'total_time': total_time
                }
            })
            
        except Exception as e:
            app.logger.error(f"Error in executor: {str(e)}")
            app.logger.error(traceback.format_exc())
            raise

@app.route('/get_translations', methods=['GET'])
def get_translations():
    if 'user_id' not in session:
        return jsonify({'error': 'User not authenticated'}), 401
    
    try:
        db = get_db()
        translations = db.execute("""
            SELECT 
                id, 
                source_text, 
                translated_text, 
                source_language, 
                target_language, 
                interpretation, 
                strftime('%Y-%m', created_at) as month,
                strftime('%Y-%m-%d', created_at) as date 
            FROM translations 
            WHERE user_id = ? 
            ORDER BY created_at DESC
        """, (session['user_id'],)).fetchall()

        translations_by_month = {}
        for t in translations:
            month = t['month']
            if month not in translations_by_month:
                translations_by_month[month] = {}
            
            date = t['date']
            if date not in translations_by_month[month]:
                translations_by_month[month][date] = []
                
            translations_by_month[month][date].append({
                'id': t['id'],
                'source_text': t['source_text'],
                'translated_text': t['translated_text'],
                'source_language': t['source_language'],
                'target_language': t['target_language'],
                'interpretation': t['interpretation']
            })

        return jsonify({'translations': translations_by_month})
    except Exception as e:
        app.logger.error(f"Error fetching translations: {str(e)}")
        app.logger.error(traceback.format_exc())
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
        app.logger.error(f"Error deleting translation: {str(e)}")
        app.logger.error(traceback.format_exc())
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
                           user_id INTEGER,
                           source_text TEXT,
                           translated_text TEXT,
                           source_language TEXT,
                           target_language TEXT,
                           interpretation TEXT,
                           created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        # 사용자의 번역 기록 복사
        translations = src_db.execute("SELECT user_id, source_text, translated_text, source_language, target_language, interpretation, created_at FROM translations WHERE user_id = ?", (session['user_id'],)).fetchall()
        dst_db.executemany("INSERT INTO translations (user_id, source_text, translated_text, source_language, target_language, interpretation, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", translations)

        dst_db.commit()
        dst_db.close()

        return send_file(
            temp_file_path,
            as_attachment=True,
            download_name='translations_backup.db',
            mimetype='application/x-sqlite3'
        )
    except Exception as e:
        app.logger.error(f"Database export error: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({'error': '데이터베이스 추출 중 오류가 발생했습니다.'}), 500
    finally:
        # 임시 파일 삭제
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as e:
                app.logger.error(f"Error deleting temporary file: {str(e)}")

@app.route('/static/service-worker.js')
def serve_service_worker():
    return app.send_static_file('service-worker.js')

@app.route('/static/manifest.json')
def serve_manifest():
    return app.send_static_file('manifest.json')

if __name__ == '__main__':
    app.run(debug=True)
