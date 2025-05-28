import os
import secrets
import sqlite3
import tempfile
import traceback
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# 서버리스 환경에서 안전한 import
try:
    from dotenv import load_dotenv
    load_dotenv()  # 로컬 개발용
except ImportError:
    pass  # 서버리스 환경에서는 python-dotenv가 없을 수도 있음

from flask import Flask, g, jsonify, redirect, render_template, request, send_file, session, url_for, Response, stream_with_context, flash
from openai import OpenAI
from werkzeug.security import check_password_hash, generate_password_hash
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback_secret_key_for_development')
app.permanent_session_lifetime = timedelta(days=90)

# OpenAI 클라이언트 초기화 (글로벌 변수로 재사용)
openai_client = None

def get_openai_client():
    global openai_client
    if openai_client is None:
        try:
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                app.logger.error("OPENAI_API_KEY environment variable not found")
                raise ValueError("OpenAI API 키가 설정되지 않았습니다.")
            
            # 개행 문자, 공백, 따옴표 제거 (중요!)
            api_key = api_key.strip().strip('"').strip("'")
            
            # API 키 형식 검증
            if not api_key.startswith('sk-'):
                app.logger.error(f"Invalid API key format. Key starts with: {api_key[:10]}...")
                raise ValueError("유효하지 않은 OpenAI API 키 형식입니다.")
            
            # 길이 검증 (일반적으로 OpenAI API 키는 매우 긺)
            if len(api_key) < 50:
                app.logger.error(f"API key too short: {len(api_key)} characters")
                raise ValueError("API 키가 너무 짧습니다.")
                
            app.logger.info(f"OpenAI API 키 로드 완료 (길이: {len(api_key)})")
            openai_client = OpenAI(api_key=api_key)
            
        except Exception as e:
            app.logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            raise
            
    return openai_client

# 스레드 풀 생성 (서버리스 환경에서는 제한적 사용)
executor = ThreadPoolExecutor(max_workers=2)

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

@app.route('/health')
def health():
    """헬스체크 엔드포인트"""
    return jsonify({
        'status': 'healthy',
        'message': 'Flask app is running',
        'has_openai_key': bool(os.getenv('OPENAI_API_KEY'))
    })

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
    
    try:
        client = get_openai_client()
        # 비동기 처리 및 최신 API 문법 적용
        translation_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a professional translator specializing in nuanced and contextually accurate translations. (번역 결과에 따옴표를 넣지 마세요)"},
                {"role": "user", "content": translation_prompt}
            ],
            temperature=0.3,  # 출력 안정성 개선
            max_tokens=2000,  # 최대 토큰 수 명시적 지정
            timeout=25  # 서버리스 환경에서 타임아웃 설정
        )
        
        # 불필요한 인코딩/디코딩 제거
        result = translation_response.choices[0].message.content.strip()
        return result, (datetime.now() - start_time).total_seconds()
        
    except Exception as e:
        app.logger.error(f"OpenAI API error in translate_text: {str(e)}")
        raise Exception(f"번역 API 호출 실패: {str(e)}")

def interpret_text_stream(text, source_language, target_language):
    interpretation_prompt = f"다음 {'영어 원문' if source_language == '영어' else '영어 번역문'}의 뉘앙스와 의미를 한국어로 자세히 설명해주세요: '{text}'"
    
    try:
        client = get_openai_client()
        # 스트리밍 최적화
        stream = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "당신은 영어 표현의 뉘앙스를 한국어로 설명하는 전문가입니다."},
                {"role": "user", "content": interpretation_prompt}
            ],
            stream=True,
            temperature=0.5,
            top_p=0.9,
            timeout=25
        )
        
        return stream
        
    except Exception as e:
        app.logger.error(f"OpenAI API error in interpret_text_stream: {str(e)}")
        raise Exception(f"해석 API 호출 실패: {str(e)}")

def interpret_text(text, source_language, target_language):
    """텍스트 해석 함수 (비스트리밍)"""
    start_time = datetime.now()
    interpretation_prompt = f"다음 {'영어 원문' if source_language == '영어' else '영어 번역문'}의 뉘앙스와 의미를 한국어로 자세히 설명해주세요: '{text}'"
    
    try:
        client = get_openai_client()
        interpretation_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "당신은 영어 표현의 뉘앙스를 한국어로 설명하는 전문가입니다."},
                {"role": "user", "content": interpretation_prompt}
            ],
            temperature=0.5,
            max_tokens=2000,
            timeout=25
        )
        
        result = interpretation_response.choices[0].message.content.strip()
        return result, (datetime.now() - start_time).total_seconds()
        
    except Exception as e:
        app.logger.error(f"OpenAI API error in interpret_text: {str(e)}")
        raise Exception(f"해석 API 호출 실패: {str(e)}")

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

@app.route('/debug_env', methods=['GET'])
def debug_env():
    """환경 변수 디버깅용 엔드포인트 (운영 환경에서는 제거 필요)"""
    try:
        api_key = os.getenv('OPENAI_API_KEY')
        return jsonify({
            'has_api_key': bool(api_key),
            'api_key_length': len(api_key) if api_key else 0,
            'api_key_starts_with_sk': api_key.startswith('sk-') if api_key else False,
            'api_key_first_10': api_key[:10] if api_key else 'None',
            'all_env_keys': list(os.environ.keys())
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
            app.logger.warning("Invalid request format - no JSON data")
            return jsonify({'error': '잘못된 요청 형식입니다.'}), 400
            
        data = request.json
        text = data.get('text', '').strip()
        source_language = data.get('source_language', '').strip()
        target_language = data.get('target_language', '').strip()
        
        app.logger.info(f"Translation request: {len(text)} chars, {source_language} -> {target_language}")
        
        # 입력 검증
        if not text:
            app.logger.warning("Empty text provided")
            return jsonify({'error': '번역할 텍스트를 입력해주세요.'}), 400
        if not source_language or not target_language:
            app.logger.warning(f"Missing languages: source={source_language}, target={target_language}")
            return jsonify({'error': '언어를 선택해주세요.'}), 400
        
        # OpenAI API 키 확인
        try:
            get_openai_client()  # 클라이언트 초기화 테스트
        except ValueError as e:
            app.logger.error(f"OpenAI API key error: {str(e)}")
            return jsonify({'error': 'API 설정에 문제가 있습니다.'}), 500
        
        # 텍스트 길이 제한 (서버리스 환경 고려)
        if len(text) > 5000:
            app.logger.warning(f"Text too long: {len(text)} chars")
            return jsonify({'error': '텍스트가 너무 깁니다. (최대 5000자)'}), 400
        
        # 번역 실행
        translation, translation_time = translate_text(text, source_language, target_language)
        
        app.logger.info(f"Translation completed in {translation_time:.2f}s")
        return jsonify({
            'translation': translation,
            'timing': {'translation_time': translation_time}
        })
        
    except Exception as e:
        error_msg = str(e)
        app.logger.error(f"Translation error: {error_msg}")
        app.logger.error(traceback.format_exc())
        
        # 더 구체적인 에러 메시지 제공
        if "API 호출 실패" in error_msg:
            return jsonify({'error': error_msg}), 500
        elif "timeout" in error_msg.lower():
            return jsonify({'error': '요청 시간이 초과되었습니다. 다시 시도해주세요.'}), 504
        elif "rate limit" in error_msg.lower():
            return jsonify({'error': 'API 사용량 한도에 도달했습니다. 잠시 후 다시 시도해주세요.'}), 429
        else:
            return jsonify({'error': f'번역 중 오류가 발생했습니다: {error_msg}'}), 500

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

@app.route('/test_api', methods=['GET'])
def test_api():
    """API 연결 테스트 엔드포인트"""
    try:
        client = get_openai_client()
        # 매우 간단한 API 호출로 테스트
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5
        )
        return jsonify({
            'success': True,
            'response': response.choices[0].message.content
        })
    except Exception as e:
        app.logger.error(f"API test error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }), 500

if __name__ == '__main__':
    app.run(debug=True)

# Vercel 서버리스 함수용 - 이것이 핵심!
# Vercel은 app 변수를 찾아서 WSGI 앱으로 실행합니다
# 추가 핸들러 불필요