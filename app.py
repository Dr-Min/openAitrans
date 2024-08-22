from flask import Flask, render_template, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv
import os

app = Flask(__name__)

# .env 파일에서 환경 변수 로드
load_dotenv()

# OpenAI 클라이언트 초기화
client = OpenAI()

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
            model="gpt-3.5-turbo",
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
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "당신은 영어 문장의 뉘앙스를 한국어로 설명하는 전문가입니다."},
                {"role": "user", "content": interpretation_prompt}
            ]
        )
        interpretation = interpretation_response.choices[0].message.content.strip()

        return jsonify({
            'translation': translation,
            'interpretation': interpretation
        })
    except Exception as e:
        app.logger.error(f"An error occurred: {str(e)}")
        return jsonify({'error': '번역 중 오류가 발생했습니다.'}), 500

if __name__ == '__main__':
    app.run(debug=True)
