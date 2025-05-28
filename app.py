import os
import secrets
import sqlite3
import tempfile
import traceback
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from flask import Flask, g, jsonify, redirect, render_template, request, send_file, session, url_for, Response, stream_with_context, flash
from openai import OpenAI
from werkzeug.security import check_password_hash, generate_password_hash
from concurrent.futures import ThreadPoolExecutor, as_completed
import json


app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
app.permanent_session_lifetime = timedelta(days=90)

# .env 파일에서 환경 변수 로드
load_dotenv()

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# 스레드 풀 생성
executor = ThreadPoolExecutor(max_workers=10)

# 데이터베이스 연결
def get_db():
    return None

@app.teardown_appcontext
def close_db(error):
    pass

# 데이터베이스 초기화
def init_db():
    pass

# 앱 시작 시 데이터베이스 초기화
# with app.app_context():
#     init_db()

@app.route('/')
def index():
    # 임시로 세션 검사 제거
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    # 임시로 회원가입 기능 비활성화
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    # 임시로 로그인 기능 비활성화
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    # 임시로 로그아웃 기능 비활성화
    return redirect(url_for('index'))

def save_translation(user_id, source_text, translated_text, source_language, target_language, interpretation):
    # 서버리스 환경에서 임시로 저장 기능 비활성화
    return True

def translate_text(text, source_language, target_language):
    start_time = datetime.now()
    translation_prompt = f"Translate the following {source_language} text to {target_language}, providing a natural and accurate translation that captures the nuance and context: '{text}'"
    
    # 비동기 처리 및 최신 API 문법 적용
    translation_response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a professional translator specializing in nuanced and contextually accurate translations. (번역 결과에 따옴표를 넣지 마세요)"},
            {"role": "user", "content": translation_prompt}
        ],
        temperature=0.3,  # 출력 안정성 개선
        max_tokens=2000  # 최대 토큰 수 명시적 지정
    )
    
    # 불필요한 인코딩/디코딩 제거
    result = translation_response.choices[0].message.content.strip()
    return result, (datetime.now() - start_time).total_seconds()

def interpret_text_stream(text, source_language, target_language):
    interpretation_prompt = f"다음 {'영어 원문' if source_language == '영어' else '영어 번역문'}의 뉘앙스와 의미를 한국어로 자세히 설명해주세요: '{text}'"
    
    # 스트리밍 최적화
    stream = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "당신은 영어 표현의 뉘앙스를 한국어로 설명하는 전문가입니다."},
            {"role": "user", "content": interpretation_prompt}
        ],
        stream=True,
        temperature=0.5,
        top_p=0.9
    )
    
    return stream

def interpret_text(text, source_language, target_language):
    """텍스트 해석 함수 (비스트리밍)"""
    start_time = datetime.now()
    interpretation_prompt = f"다음 {'영어 원문' if source_language == '영어' else '영어 번역문'}의 뉘앙스와 의미를 한국어로 자세히 설명해주세요: '{text}'"
    
    interpretation_response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "당신은 영어 표현의 뉘앙스를 한국어로 설명하는 전문가입니다."},
            {"role": "user", "content": interpretation_prompt}
        ],
        temperature=0.5,
        max_tokens=2000
    )
    
    result = interpretation_response.choices[0].message.content.strip()
    return result, (datetime.now() - start_time).total_seconds()

@app.route('/interpret_stream', methods=['POST'])
def interpret_stream():
    data = request.json
    text = data.get('text', '')
    translation = data.get('translation', '')
    source_language = data.get('source_language', '')
    target_language = data.get('target_language', '')
    
    def generate():
        full_text = ""
        try:
            stream = interpret_text_stream(
                text if source_language == "영어" else translation,
                source_language,
                target_language
            )
            
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    # 스트림 결과도 JSON-safe하게 처리
                    content = content.encode('utf-8').decode('utf-8')
                    full_text += content
                    yield f"data: {json.dumps({'content': content, 'full_text': full_text})}\n\n"
            
            yield f"data: {json.dumps({'done': True})}\n\n"
            
        except Exception as e:
            app.logger.error(f"Streaming error: {str(e)}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/translate', methods=['POST'])
def translate():
    try:
        data = request.json
        # 병렬 처리 구현
        with ThreadPoolExecutor() as executor:
            future = executor.submit(
                translate_text,
                data['text'],
                data['source_language'],
                data['target_language']
            )
            translation, translation_time = future.result(timeout=30)
        
        return jsonify({
            'translation': translation,
            'timing': {'translation_time': translation_time}
        })
        
    except Exception as e:
        app.logger.error(f"Translation error: {str(e)}")
        return jsonify({'error': '번역 처리 중 오류 발생'}), 500

@app.route('/get_translations', methods=['GET'])
def get_translations():
    # 임시로 빈 결과 반환
    return jsonify({'translations': {}})

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
        # 임시 파일 생성 ㅎㅇㅇ
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

@app.route('/translate_only', methods=['POST'])
def translate_only():
    try:
        # 요청 데이터 검증
        if not request.json:
            return jsonify({'error': '잘못된 요청 형식입니다.'}), 400
            
        data = request.json
        text = data.get('text', '').strip()
        source_language = data.get('source_language', '').strip()
        target_language = data.get('target_language', '').strip()
        
        # 입력 검증
        if not text:
            return jsonify({'error': '번역할 텍스트를 입력해주세요.'}), 400
        if not source_language or not target_language:
            return jsonify({'error': '언어를 선택해주세요.'}), 400
        
        # OpenAI API 키 확인
        if not os.getenv('OPENAI_API_KEY'):
            app.logger.error("OpenAI API key not found")
            return jsonify({'error': 'API 설정에 문제가 있습니다.'}), 500
        
        translation, _ = translate_text(text, source_language, target_language)
        return jsonify({'translation': translation})
        
    except Exception as e:
        app.logger.error(f"Translation error: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({'error': f'번역 중 오류가 발생했습니다: {str(e)}'}), 500

@app.route('/interpret_and_save', methods=['POST'])
def interpret_and_save():
    try:
        # 요청 데이터 검증
        if not request.json:
            return jsonify({'error': '잘못된 요청 형식입니다.'}), 400
            
        data = request.json
        text = data.get('text', '').strip()
        translation = data.get('translation', '').strip()
        source_language = data.get('source_language', '').strip()
        target_language = data.get('target_language', '').strip()
        
        # 입력 검증
        if not text or not translation:
            return jsonify({'error': '필수 데이터가 누락되었습니다.'}), 400
        if not source_language or not target_language:
            return jsonify({'error': '언어 정보가 누락되었습니다.'}), 400
        
        # OpenAI API 키 확인
        if not os.getenv('OPENAI_API_KEY'):
            app.logger.error("OpenAI API key not found")
            return jsonify({'error': 'API 설정에 문제가 있습니다.'}), 500
        
        interpretation, interpretation_time = interpret_text(
            text if source_language == "영어" else translation, 
            source_language, 
            target_language
        )
        
        return jsonify({
            'interpretation': interpretation,
            'timing': {
                'interpretation_time': interpretation_time
            }
        })
        
    except Exception as e:
        app.logger.error(f"Interpretation error: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({'error': f'해석 중 오류가 발생했습니다: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)