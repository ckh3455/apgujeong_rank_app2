import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.pyplot as plt
from matplotlib import font_manager


def setup_korean_font():
    """
    Streamlit Cloud(리눅스)에서 Matplotlib 한글 깨짐을 막기 위한 폰트 설정:
    - 레포의 ./fonts 폴더에 .ttf/.otf 폰트 파일을 넣으면 자동으로 탐지/등록합니다.
    - 없으면 시스템 설치 폰트를 탐색합니다.
    """
    try:
        from pathlib import Path

        here = Path(__file__).resolve().parent
        fonts_dir = here / "fonts"

        # 레포 포함 폰트 자동 탐지
        if fonts_dir.exists() and fonts_dir.is_dir():
            font_files = []
            for ext in ("*.ttf", "*.otf", "*.ttc"):
                font_files.extend(sorted(fonts_dir.glob(ext)))

            # 선호 키워드(가능하면 한글 폰트 우선)
            prefer = ["notosanskr", "noto sans kr", "notosanscjk", "nanum", "malgun", "applegothic"]

            def score(p: Path) -> int:
                name = p.name.lower()
                for i, kw in enumerate(prefer):
                    if kw.replace(" ", "") in name.replace(" ", ""):
                        return 100 - i
                return 0

            font_files.sort(key=score, reverse=True)

            for fp in font_files:
                try:
                    font_manager.fontManager.addfont(str(fp))

                    # 캐시를 다시 읽도록 유도(환경에 따라 필요)
                    try:
                        font_manager._load_fontmanager(try_read_cache=False)
                    except Exception:
                        pass

                    name = font_manager.FontProperties(fname=str(fp)).get_name()
                    plt.rcParams["font.family"] = name
                    plt.rcParams["font.sans-serif"] = [name]
                    plt.rcParams["axes.unicode_minus"] = False
                    return name
                except Exception:
                    continue

        # 시스템 설치 폰트 탐색
        candidates = ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans KR", "Noto Sans CJK KR"]
        for name in candidates:
            try:
                _ = font_manager.findfont(font_manager.FontProperties(family=name), fallback_to_default=False)
                plt.rcParams["font.family"] = name
                plt.rcParams["font.sans-serif"] = [name]
                plt.rcParams["axes.unicode_minus"] = False
                return name
            except Exception:
                continue

        plt.rcParams["axes.unicode_minus"] = False
        return None

    except Exception:
        return None


# =========================
# 기본(하드코딩) 시트 설정
# - Secrets에 값을 넣으면 그 값이 우선합니다.
# =========================
DEFAULT_MAIN_SHEET_ID = "1QGSM-mICX9KYa5Izym6sFKVaWwO-o0j86V-KmJ-w0IM"
DEFAULT_LOG_SHEET_ID = "1-V5Ux8yto_8WE6epumN1aWT_D5t_1Dx14VWBZ0SvbbU"
DEFAULT_MAIN_GID = 0
DEFAULT_LOG_GID = 0
DEFAULT_MAX_DATA_ROWS = 10337


# =========================
# 사용자 안내/라벨
# =========================
APP_DESCRIPTION = (
    "⚠️ 데이터는 **2016년부터 2025년까지  공동주택 공시가격(공주가)** 을 바탕으로 계산한 것으로, "
    "재건축 시 **실행될 감정평가액과 차이**가 있을 수 있습니다.\n\n"
    "이 앱은 **구역 → 동 → 호**를 선택하면 같은 구역과 압구정 전체의  **환산감정가(억)** 기준으로 "
    "**경쟁 순위**(공동이면 같은 순위, 다음 순위는 건너뜀)를 보여줍니다.\n\n"
    "- **환산감정가(억)** = 공시가격(억) × 배수\n"
    "- 배수는 사용자 입력값(기본 2.0)입니다.\n"
)

ZONE_CHOICES = ["압구정2구역", "압구정3구역", "압구정4구역", "압구정5구역", "압구정6구역"]
APL_ZONE_LABEL = "압구정 전체"

DEFAULT_MULTIPLIER = 2.0

# 순위 라벨(그래프 숫자)
SHOW_RANK_LABELS = True
RANK_LABEL_FONTSIZE = 9
RANK_LABEL_Y_OFFSET = -22  # (음수일수록 위로 더 올라감)
RANK_LABEL_BOLD = True

# =========================
# 한글 폰트 설정 (Matplotlib)
# =========================
def set_korean_matplotlib_font() -> str | None:
    candidates = ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans KR", "Noto Sans CJK KR"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["font.sans-serif"] = [name]
            matplotlib.rcParams["axes.unicode_minus"] = False
            return name
    matplotlib.rcParams["axes.unicode_minus"] = False
    return None


# 한글 폰트 설정: 레포 내 ./fonts 폴더 폰트 우선 등록 후, 시스템 폰트로 fallback
@st.cache_resource(show_spinner=False)
def init_matplotlib_font() -> str | None:
    name = setup_korean_font()
    if not name:
        name = set_korean_matplotlib_font()
    return name

_ = init_matplotlib_font()


# =========================
# UI 기본
# =========================
st.set_page_config(page_title="압구정 공시가격 랭킹", layout="centered")
# =========================
# 배포/실행을 위한 Secrets 검증
# =========================
def _validate_runtime_config() -> None:
    missing = []
    if "gcp_service_account" not in st.secrets:
        missing.append("gcp_service_account")
    if missing:
        st.error(
            "Secrets 설정이 필요합니다.\n\n"
            f"누락 항목: {', '.join(missing)}\n\n"
            "Streamlit Cloud의 Settings → Secrets에서 값을 설정하세요."
        )
        st.stop()


# =========================
# 시트 ID / GID / 최대 행 수
# =========================
MAIN_SHEET_ID = st.secrets.get("MAIN_SHEET_ID", DEFAULT_MAIN_SHEET_ID)
LOG_SHEET_ID = st.secrets.get("LOG_SHEET_ID", DEFAULT_LOG_SHEET_ID)
MAIN_GID = int(st.secrets.get("MAIN_GID", DEFAULT_MAIN_GID))
LOG_GID = int(st.secrets.get("LOG_GID", DEFAULT_LOG_GID))
MAX_DATA_ROWS = int(st.secrets.get("MAX_DATA_ROWS", DEFAULT_MAX_DATA_ROWS))


# =========================
# Google Sheets 로드/전처리 유틸
# =========================
@st.cache_data(show_spinner=False, ttl=60 * 60)
def load_main_data(sheet_id: str, gid: int, max_rows: int) -> pd.DataFrame:
    import gspread
    from google.oauth2.service_account import Credentials

    creds_info = st.secrets.get("gcp_service_account", None)
    if creds_info is None:
        raise RuntimeError("Secrets에 gcp_service_account가 없습니다. Streamlit Secrets를 확인하세요.")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
    gc = gspread.authorize(credentials)

    sh = gc.open_by_key(sheet_id)

    # gid로 워크시트 선택
    ws = None
    for w in sh.worksheets():
        if w.id == gid:
            ws = w
            break
    if ws is None:
        # gid가 0인 경우 첫 시트로
        ws = sh.get_worksheet(0)

    values = ws.get_all_values()
    if not values:
        return pd.DataFrame()

    header = values[0]
    rows = values[1 : max_rows + 1]

    df = pd.DataFrame(rows, columns=header)
    return df


def _to_float(x):
    if x is None:
        return None
    s = str(x).strip()
    if s == "":
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return None


def _clean_text(x):
    if x is None:
        return ""
    return str(x).strip()


def preprocess_main_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df.columns = [_clean_text(c) for c in df.columns]

    # 원본 컬럼명에 맞춘 필드 후보 탐색
    zone_col = None
    dong_col = None
    ho_col = None

    for c in df.columns:
        if zone_col is None and ("구역" in c):
            zone_col = c
        if dong_col is None and ("동" == c or "동명" in c or "동 " in c):
            dong_col = c
        if ho_col is None and ("호" == c or "호수" in c or "호 " in c):
            ho_col = c

    # 공시가격(억) 후보: 2025 또는 최신 연도 우선
    price_cols = [c for c in df.columns if re.search(r"(20\d{2}).*(공시|공주|공시가격|공주가)", c)]
    if not price_cols:
        price_cols = [c for c in df.columns if "2025" in c]

    def year_of(col):
        m = re.search(r"(20\d{2})", col)
        return int(m.group(1)) if m else 0

    price_cols = sorted(price_cols, key=year_of, reverse=True)

    if zone_col is None or dong_col is None or ho_col is None or not price_cols:
        return df

    latest_price_col = price_cols[0]

    df[zone_col] = df[zone_col].apply(_clean_text)
    df[dong_col] = df[dong_col].apply(_clean_text)
    df[ho_col] = df[ho_col].apply(_clean_text)
    df[latest_price_col] = df[latest_price_col].apply(_to_float)

    df = df[df[zone_col] != ""]
    df = df[df[dong_col] != ""]
    df = df[df[ho_col] != ""]
    df = df[df[latest_price_col].notna()]

    df = df.rename(
        columns={
            zone_col: "구역",
            dong_col: "동",
            ho_col: "호",
            latest_price_col: "공시가격(억)",
        }
    ).copy()

    return df


def compute_rank(df: pd.DataFrame, multiplier: float) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["환산감정가(억)"] = df["공시가격(억)"] * float(multiplier)

    # 압구정 전체 순위
    df = df.sort_values(["환산감정가(억)"], ascending=False).reset_index(drop=True)

    # competition ranking (동점 동일 순위, 다음 순위는 건너뜀)
    df["압구정전체_순위"] = df["환산감정가(억)"].rank(method="min", ascending=False).astype(int)

    # 구역 내 순위
    df["구역내_순위"] = (
        df.groupby("구역")["환산감정가(억)"].rank(method="min", ascending=False).astype(int)
    )

    return df


def plot_zone_hist(df_zone: pd.DataFrame, title: str):
    if df_zone is None or df_zone.empty:
        return None

    fig, ax = plt.subplots()
    ax.hist(df_zone["환산감정가(억)"].dropna(), bins=20)
    ax.set_title(title)
    ax.set_xlabel("환산감정가(억)")
    ax.set_ylabel("빈도")
    plt.tight_layout()
    return fig


# =========================
# 앱 실행
# =========================
st.title("압구정 공시가격 랭킹")
st.markdown(APP_DESCRIPTION)

_validate_runtime_config()

with st.sidebar:
    st.header("설정")
    multiplier = st.number_input("배수", min_value=0.1, max_value=10.0, value=float(DEFAULT_MULTIPLIER), step=0.1)
    zone_choice = st.selectbox("구역 선택", [APL_ZONE_LABEL] + ZONE_CHOICES, index=0)

# 데이터 로드
try:
    raw_df = load_main_data(MAIN_SHEET_ID, MAIN_GID, MAX_DATA_ROWS)
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

df = preprocess_main_df(raw_df)
if df is None or df.empty or "공시가격(억)" not in df.columns:
    st.warning("데이터가 비어있거나 전처리 조건에 맞지 않습니다. (원본 시트 컬럼명을 확인하세요)")
    st.dataframe(raw_df.head(20))
    st.stop()

df_rank = compute_rank(df, multiplier)

# 필터
if zone_choice != APL_ZONE_LABEL:
    df_view = df_rank[df_rank["구역"] == zone_choice].copy()
else:
    df_view = df_rank.copy()

# 동/호 선택 UI
col1, col2, col3 = st.columns(3)

with col1:
    zone_for_selector = zone_choice if zone_choice != APL_ZONE_LABEL else st.selectbox("구역(선택)", ZONE_CHOICES, index=0)

with col2:
    dong_list = sorted(df_rank[df_rank["구역"] == zone_for_selector]["동"].unique())
    dong_choice = st.selectbox("동 선택", dong_list)

with col3:
    ho_list = df_rank[(df_rank["구역"] == zone_for_selector) & (df_rank["동"] == dong_choice)]["호"].unique().tolist()
    ho_choice = st.selectbox("호 선택", ho_list)

# 선택 결과
sel = df_rank[(df_rank["구역"] == zone_for_selector) & (df_rank["동"] == dong_choice) & (df_rank["호"] == ho_choice)]
if sel.empty:
    st.warning("선택된 동/호에 해당하는 데이터가 없습니다.")
else:
    row = sel.iloc[0]
    st.subheader("선택 결과")
    st.write(
        {
            "구역": row["구역"],
            "동": row["동"],
            "호": row["호"],
            "공시가격(억)": row["공시가격(억)"],
            "배수": float(multiplier),
            "환산감정가(억)": row["환산감정가(억)"],
            "구역내 순위": int(row["구역내_순위"]),
            "압구정전체 순위": int(row["압구정전체_순위"]),
        }
    )

# 테이블 표시
st.subheader("랭킹 테이블")
show_cols = ["구역", "동", "호", "공시가격(억)", "환산감정가(억)", "구역내_순위", "압구정전체_순위"]
st.dataframe(df_view[show_cols].sort_values(["환산감정가(억)"], ascending=False).reset_index(drop=True))

# 그래프(한글 확인)
st.subheader("분포 그래프")
if zone_choice == APL_ZONE_LABEL:
    fig = plot_zone_hist(df_rank, "압구정 전체 환산감정가 분포")
else:
    fig = plot_zone_hist(df_rank[df_rank["구역"] == zone_choice], f"{zone_choice} 환산감정가 분포")

if fig is not None:
    st.pyplot(fig)

# 실행 시각(서울)
now = datetime.now(ZoneInfo("Asia/Seoul"))
st.caption(f"마지막 갱신: {now:%Y-%m-%d %H:%M:%S} (Asia/Seoul)")
