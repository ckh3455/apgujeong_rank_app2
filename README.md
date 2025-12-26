# 압구정 공시가격 랭킹 (Streamlit)

로컬에서 실행하던 Streamlit 앱을 GitHub + Streamlit Community Cloud로 배포 가능한 형태로 정리한 버전입니다.

## 1) 필수 준비물

- Python 3.10+ 권장
- Google 서비스계정(Service Account) JSON
- (읽기/쓰기 대상) Google Spreadsheet 2개
  - 메인 데이터 시트 (읽기)
  - 조회 로그 시트 (append용, 선택)

## 2) 로컬 실행

### (1) 설치

```bash
pip install -r requirements.txt
```

### (2) Secrets 설정 (로컬 전용)

레포 루트에 아래 파일을 만드세요. **이 파일은 Git에 올리지 않습니다.**

`.streamlit/secrets.toml`

#### 옵션 A (추천): gcp_service_account를 사용 (Cloud와 동일한 방식)

```toml
main_sheet_id = "메인 스프레드시트 ID"
main_gid = 0
max_data_rows = 10337

# 선택(없으면 로그 기록 비활성화)
log_sheet_id = "로그 스프레드시트 ID"
log_gid = 0

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "...@....iam.gserviceaccount.com"
client_id = "..."
token_uri = "https://oauth2.googleapis.com/token"
```

#### 옵션 B: SERVICE_ACCOUNT_FILE 경로 사용 (로컬에서만 권장)

```toml
SERVICE_ACCOUNT_FILE = "/절대경로/your-service-account.json"

main_sheet_id = "메인 스프레드시트 ID"
main_gid = 0

# 선택
log_sheet_id = "로그 스프레드시트 ID"
log_gid = 0
```

### (3) 실행

```bash
streamlit run app.py
```

## 3) Google Sheets 권한

서비스계정의 `client_email`을 아래 시트에 공유(편집 권한 권장)해 주세요.

- 메인 스프레드시트 (데이터 읽기)
- 로그 스프레드시트 (행 추가)

편집 권한이 없으면 로그 append에서 실패할 수 있습니다.

## 4) Streamlit Community Cloud 배포

1. Streamlit Community Cloud 로그인
2. `New app` → `From GitHub`
3. Repository / Branch 선택 (`main`)
4. `Main file path`에 `app.py` 지정
5. `Settings → Secrets`에 아래 TOML을 그대로 등록

```toml
main_sheet_id = "메인 스프레드시트 ID"
main_gid = 0
max_data_rows = 10337

log_sheet_id = "로그 스프레드시트 ID"
log_gid = 0

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "...@....iam.gserviceaccount.com"
client_id = "..."
token_uri = "https://oauth2.googleapis.com/token"
```

## 5) 주의 사항 (보안)

- 서비스계정 키는 **Secrets로만** 관리합니다(절대 커밋 금지). 스프레드시트 ID는 기본값이 코드에 포함되어 있으나, Secrets로 언제든 덮어쓸 수 있습니다.
- `.streamlit/secrets.toml`은 `.gitignore`에 포함되어 커밋되지 않도록 되어 있습니다.
