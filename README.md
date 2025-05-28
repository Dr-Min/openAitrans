# AI 번역기 - OpenAI Translation App

로컬과 Vercel 서버리스 환경 모두에서 작동하는 AI 번역 애플리케이션입니다.

## 주요 기능

- OpenAI GPT-4o를 사용한 정확한 번역
- 실시간 스트리밍 해석 기능
- 웹 인터페이스 제공
- PWA (Progressive Web App) 지원

## 환경 설정

### 로컬 개발

1. `.env` 파일 생성:

```
OPENAI_API_KEY=your_openai_api_key_here
SECRET_KEY=your_secret_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
JWT_SECRET_KEY=your_jwt_secret_key_here
```

2. 의존성 설치:

```bash
pip install -r requirements.txt
```

3. 서버 실행:

```bash
python app.py
```

### Vercel 배포

1. **환경 변수 설정**: Vercel 대시보드에서 다음 환경 변수들을 설정하세요:

   - `OPENAI_API_KEY`: OpenAI API 키
   - `SECRET_KEY`: Flask 세션 시크릿 키
   - `ANTHROPIC_API_KEY`: Anthropic API 키 (선택사항)
   - `JWT_SECRET_KEY`: JWT 시크릿 키

2. **배포 명령어**:

```bash
vercel --prod
```

## 문제 해결

### "Connection error" 오류 (Vercel)

이 오류는 주로 다음 원인들로 발생합니다:

1. **환경 변수 미설정**: Vercel 대시보드에서 모든 필요한 환경 변수가 설정되었는지 확인
2. **API 키 오류**: OpenAI API 키가 유효하고 충분한 크레딧이 있는지 확인
3. **시간 초과**: 긴 텍스트는 5000자 이하로 제한하여 처리 시간 단축
4. **Rate Limit**: API 사용량 한도 확인

### 일반적인 해결 방법

1. Vercel 함수 로그 확인: `vercel logs`
2. 환경 변수 재설정
3. 프로젝트 재배포: `vercel --prod --force`

## 서버리스 최적화

- 함수 실행 시간: 최대 30초
- 동시 처리: 최대 2개 스레드
- 텍스트 길이 제한: 5000자
- 타임아웃 설정: 25초

## 기술 스택

- **Backend**: Flask, OpenAI API
- **Frontend**: HTML, CSS, JavaScript
- **Deployment**: Vercel Serverless Functions
- **Database**: SQLite (로컬), 메모리 기반 (서버리스)
