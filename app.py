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
        app.logger.info("데이터베이스가 성공적으로 초기화되었습니다.")
    except sqlite3.Error as e:
        app.logger.error(f"데이터베이스 초기화 오류: {e}")
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
            return "이미 존재하는 사용자명입니다"
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
        return "잘못된 사용자명 또는 비밀번호입니다"
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
    translation_prompt = f"다음 {source_language} 텍스트를 {target_language}로 번역하되, 뉘앙스와 문맥을 정확하게 반영하여 자연스럽게 번역해주세요: '{text}'"
    translation_response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "당신은 뉘앙스와 문맥을 정확히 파악하여 번역하는 전문 번역가입니다."},
            {"role": "user", "content": translation_prompt}
        ]
    )
    return translation_response.choices[0].message.content.strip()

def interpret_text(text, target_language):
    interpretation_prompt = f"다음 {target_language} 문장의 뉘앙스를 한국어로 설명해주세요: '{text}'"
    interpretation_response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": f"당신은 {target_language} 문장의 뉘앙스를 한국어로 설명하는 전문가입니다."},
            {"role": "user", "content": interpretation_prompt}
        ]
    )
    return interpretation_response.choices[0].message.content.strip()

@app.route('/translate', methods=['POST'])
def translate():
    if 'user_id' not in session:
        return jsonify({'error': '사용자 인증이 필요합니다'}), 401
    
    try:
        data = request.json
        text = data['text']
        source_language = data['source_language']
        target_language = data['target_language']

        with ThreadPoolExecutor(max_workers=2) as executor:
            # 번역과 해석을 동시에 시작
            translation_future = executor.submit(translate_text, text, source_language, target_language)
            
            # 번역 결과를 기다림
            translation = translation_future.result()
            
            # 번역 결과를 이용해 해석 시작
            interpretation_future = executor.submit(interpret_text, translation, target_language)
            
            # 해석 결과를 기다림
            interpretation = interpretation_future.result()

            # 데이터베이스에 저장 (동기적으로 수행)
            save_translation(session['user_id'], text, translation, source_language, target_language, interpretation)

        return jsonify({
            'translation': translation,
            'interpretation': interpretation
        })
    except Exception as e:
        app.logger.error(f"번역 오류: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({'error': '번역 중 오류가 발생했습니다.'}), 500

@app.route('/get_translations', methods=['GET'])
def get_translations():
    if 'user_id' not in session:
        return jsonify({'error': '사용자 인증이 필요합니다'}), 401
    
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
        app.logger.error(f"번역 기록 조회 오류: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({'error': '번역 기록을 가져오는 중 오류가 발생했습니다.'}), 500

@app.route('/delete_translation/<int:id>', methods=['DELETE'])
def delete_translation(id):
    if 'user_id' not in session:
        return jsonify({'error': '사용자 인증이 필요합니다'}), 401
    
    try:
        db = get_db()
        db.execute("DELETE FROM translations WHERE id = ? AND user_id = ?", (id, session['user_id']))
        db.commit()
        return jsonify({'message': '번역 기록이 삭제되었습니다.'}), 200
    except Exception as e:
        app.logger.error(f"번역 기록 삭제 오류: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({'error': '번역 기록 삭제 중 오류가 발생했습니다.'}), 500

@app.route('/export_db', methods=['GET'])
def export_db():
    if 'user_id' not in session:
        return jsonify({'error': '사용자 인증이 필요합니다'}), 401
    
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
        app.logger.error(f"데이터베이스 추출 오류: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({'error': '데이터베이스 추출 중 오류가 발생했습니다.'}), 500
    finally:
        # 임시 파일 삭제
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as e:
                app.logger.error(f"임시 파일 삭제 오류: {str(e)}")

if __name__ == '__main__':
    app.run(debug=True)