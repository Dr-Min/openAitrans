from flask import Flask, render_template, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv
import os
import sqlite3
from datetime import datetime

app = Flask(__name__)

# .env 파일에서 환경 변수 로드
load_dotenv()

# OpenAI 클라이언트 초기화
client = OpenAI()

# 데이터베이스 초기화
def init_db():
    conn = sqlite3.connect('translations.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS translations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  source_text TEXT,
                  translated_text TEXT,
                  source_language TEXT,
                  target_language TEXT,
                  interpretation TEXT,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# 데이터베이스 재초기화
def reinit_db():
    if os.path.exists('translations.db'):
        os.remove('translations.db')
    init_db()

# 앱 시작 시 데이터베이스 재초기화
reinit_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/translate', methods=['POST'])
def translate():
    try:
        data = request.json
        text = data['text']
        source_language = data['source_language']
        target_language = data['target_language']

        # 번역
        translation_response = client.chat.completions.create(
            model="gpt-4o-mini",
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
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 영어 문장의 뉘앙스를 한국어로 설명하는 전문가입니다."},
                {"role": "user", "content": interpretation_prompt}
            ]
        )
        interpretation = interpretation_response.choices[0].message.content.strip()

        # 데이터베이스에 저장
        conn = sqlite3.connect('translations.db')
        c = conn.cursor()
        c.execute("INSERT INTO translations (source_text, translated_text, source_language, target_language, interpretation, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                  (text, translation, source_language, target_language, interpretation, datetime.now()))
        conn.commit()
        conn.close()

        return jsonify({
            'translation': translation,
            'interpretation': interpretation
        })
    except Exception as e:
        app.logger.error(f"An error occurred: {str(e)}")
        return jsonify({'error': '번역 중 오류가 발생했습니다.'}), 500

@app.route('/get_translations', methods=['GET'])
def get_translations():
    try:
        conn = sqlite3.connect('translations.db')
        c = conn.cursor()
        c.execute("SELECT id, source_text, translated_text, source_language, target_language, interpretation, strftime('%Y-%m-%d', created_at) as date FROM translations ORDER BY created_at DESC")
        translations = c.fetchall()
        conn.close()

        translations_by_date = {}
        for t in translations:
            date = t[6]
            if date not in translations_by_date:
                translations_by_date[date] = []
            translations_by_date[date].append({
                'id': t[0],
                'source_text': t[1],
                'translated_text': t[2],
                'source_language': t[3],
                'target_language': t[4],
                'interpretation': t[5]
            })

        return jsonify({'translations': translations_by_date})
    except Exception as e:
        app.logger.error(f"An error occurred while fetching translations: {str(e)}")
        return jsonify({'error': '번역 기록을 가져오는 중 오류가 발생했습니다.'}), 500

@app.route('/delete_translation/<int:id>', methods=['DELETE'])
def delete_translation(id):
    try:
        conn = sqlite3.connect('translations.db')
        c = conn.cursor()
        c.execute("DELETE FROM translations WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        return jsonify({'message': '번역 기록이 삭제되었습니다.'}), 200
    except Exception as e:
        app.logger.error(f"An error occurred while deleting translation: {str(e)}")
        return jsonify({'error': '번역 기록 삭제 중 오류가 발생했습니다.'}), 500

if __name__ == '__main__':
    app.run(debug=True)
