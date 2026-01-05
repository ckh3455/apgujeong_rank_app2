import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib import font_manager

def setup_korean_font():
    """
    Streamlit Cloud(리눅스)에서 Matplotlib 한글 깨짐을 막기 위한 폰트 설정.
    - 레포의 ./fonts 폴더에 .ttf/.otf를 넣으면 자동으로 탐지/등록합니다.
    - 없으면 시스템 설치 폰트를 탐색합니다.
    """
    try:
        from pathlib import Path
        import os

        here = Path(__file__).resolve().parent
        fonts_dir = here / "fonts"

        # 1) 레포 포함 폰트 자동 탐지
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

        # 2) 시스템 설치 폰트 탐색
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
# - 원래 로컬 스크립트에 있던 기본값을 유지합니다.
# =========================
DEFAULT_MAIN_SHEET_ID = "1QGSM-mICX9KYa5Izym6sFKVaWwO-o0j86V-KmJ-w0IM"
DEFAULT_LOG_SHEET_ID = "1-V5Ux8yto_8WE6epumN1aWT_D5t_1Dx14VWBZ0SvbbU"
DEFAULT_MAIN_GID = 0
DEFAULT_MAIN_WORKSHEET_NAME = "공동주택 공시가격"
DEFAULT_LOG_GID = 0
DEFAULT_MAX_DATA_ROWS = 10337


# =========================
# 사용자 안내/라벨
# =========================
APP_DESCRIPTION = (
    "⚠️ 데이터는 **2016년부터 2025년까지  공동주택 공시가격(공주가)** 을 바탕으로 계산한 것으로, "
    "재건축 시 **실행될 감정평가액과 차이**가 있을 수 있습니다.\n\n"
    "이 앱은 **구역 → 동 → 호**를 선택하면 같은 구역과 압구정 전체의  **환산감정가(억)** 기준으로 "
    "**경쟁 순위**(공동이면 같은 순위, 다음 순위는 건너뜀)를 계산해 보여줍니다. "
    "재건축 과정에서 발생한 순위변화의 흐름**을 "
    "**확인 하실수 있습니다."
)

PROMO_TEXT_HTML = """
<style>
  .promo-box{
    border: 1px solid rgba(49,51,63,.15);
    border-radius: 14px;
    padding: 14px 16px;
    background: rgba(250,250,252,.75);
    margin: 10px 0 18px 0;
  }
  .promo-title{ font-size: 0.84rem; margin-bottom: 6px; }
  .promo-line{ font-size: 0.78rem; line-height: 1.08rem; }
  .promo-small{ margin-top: 6px; font-size: 0.72rem; color: rgba(49,51,63,.75); }
</style>
<div class="promo-box">
  <div class="promo-title">📞 <b>압구정 원 부동산</b></div>
  <div class="promo-line">압구정 재건축 전문 컨설팅 · <b>가열되는 순위경쟁  <div clas
  <div class="promo-line"><b>문의</b></div>
  <div class="promo-line">02-540-3334 / 최이사 Mobile 010-3065-1780</div>
  <div class="promo-small">압구정 미래가치 예측.</div>
</div>
"""


# =========================
# 설정 (Streamlit Secrets)
# - Public 레포 기준으로, 스프레드시트 ID를 코드에 하드코딩하지 않습니다.
# - 필수: main_sheet_id
# - 선택: log_sheet_id (없으면 조회 로그 기록을 건너뜁니다)
# =========================
MAIN_SPREADSHEET_ID = str(st.secrets.get("main_sheet_id", DEFAULT_MAIN_SHEET_ID)).strip()
MAIN_GID = int(st.secrets.get("main_gid", DEFAULT_MAIN_GID))
MAIN_WORKSHEET_NAME = str(st.secrets.get("main_worksheet_name", DEFAULT_MAIN_WORKSHEET_NAME)).strip()
MAX_DATA_ROWS = int(st.secrets.get("max_data_rows", DEFAULT_MAX_DATA_ROWS))

# 조회 로그 기록용 시트(선택)
LOG_SPREADSHEET_ID = str(st.secrets.get("log_sheet_id", DEFAULT_LOG_SHEET_ID)).strip()
LOG_GID = int(st.secrets.get("log_gid", DEFAULT_LOG_GID))

# =========================
# 차트 스타일(스크립트 내에서만 수정)
# =========================
ZONE_RANK_STYLE = {
    "line_color": "#1f77b4",
    "line_width": 2.5,
    "line_style": "-",
    "marker": "o",
    "marker_size": 7,
    "marker_face": "#ffffff",
    "marker_edge": "#1f77b4",
    "marker_edge_width": 1.2,
}
ALL_RANK_STYLE = {
    "line_color": "#d62728",
    "line_width": 2.5,
    "line_style": "-",
    "marker": "o",
    "marker_size": 7,
    "marker_face": "#ffffff",
    "marker_edge": "#d62728",
    "marker_edge_width": 1.2,
}
SEL_PRICE_STYLE = {
    "line_color": "#2ca02c",
    "line_width": 2.5,
    "line_style": "-",
    "marker": "o",
    "marker_size": 7,
    "marker_face": "#ffffff",
    "marker_edge": "#2ca02c",
    "marker_edge_width": 1.2,
}
CMP_PRICE_STYLE = {
    "line_color": "#9467bd",
    "line_width": 2.5,
    "line_style": "--",
    "marker": "s",
    "marker_size": 7,
    "marker_face": "#ffffff",
    "marker_edge": "#9467bd",
    "marker_edge_width": 1.2,
}

# 레이싱차트 스타일(3번 비교 그래프)
SEL_BAR_STYLE = {
    "face_color": "#2ca02c",
    "edge_color": "#145a32",
    "linewidth": 1.2,
    "alpha": 0.85,
    "hatch": "",
}
CMP_BAR_STYLE = {
    "face_color": "#9467bd",
    "edge_color": "#4a235a",
    "linewidth": 1.2,
    "alpha": 0.85,
    "hatch": "//",
}

# 순위 라벨(그래프 숫자)
SHOW_RANK_LABELS = True
RANK_LABEL_FONTSIZE = 9
RANK_LABEL_Y_OFFSET = -22  # (음수일수록 위로 더 올라감)
RANK_LABEL_BOLD = True

# 표/그래프 높이(좌우 패널 맞춤)
RANK_PANEL_HEIGHT_PX = 560   # 좌측 표, 우측 그래프를 동일 높이로 맞춤
RANK_FIG_DPI = 130
RANK_FIG_HEIGHT_IN = RANK_PANEL_HEIGHT_PX / RANK_FIG_DPI
RANK_TABLE_ROW_HEIGHT_PX = 24  # CSS로 줄일 행 높이


# =========================
# 한글 폰트 설정 (Matplotlib)
# =========================
def set_korean_matplotlib_font() -> str | None:
    candidates = ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans KR", "Noto Sans CJK KR"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            matplotlib.rcParams["font.family"] = name
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
    missing: list[str] = []

    if not MAIN_SPREADSHEET_ID:
        missing.append("main_sheet_id")

    has_sa_info = ("gcp_service_account" in st.secrets) or bool(str(st.secrets.get("SERVICE_ACCOUNT_FILE", "")).strip())
    if not has_sa_info:
        missing.append("gcp_service_account 또는 SERVICE_ACCOUNT_FILE")

    if missing:
        st.error(
            "앱 실행에 필요한 Streamlit Secrets 설정이 없습니다(인증 정보가 필요합니다): "
            + ", ".join(missing)
            + "\n\n"
            + "Streamlit Cloud에서는 Settings → Secrets에 아래 예시를 TOML로 등록하세요.\n\n"
            + "main_sheet_id = \"메인 스프레드시트 ID\"\n"
            + "main_gid = 0\n"
            + "max_data_rows = 10337\n\n"
            + "log_sheet_id = \"(선택) 로그 스프레드시트 ID\"\n"
            + "log_gid = 0\n\n"
            + "[gcp_service_account]\n"
            + "type = \"service_account\"\n"
            + "project_id = \"...\"\n"
            + "private_key_id = \"...\"\n"
            + "private_key = \"-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n\"\n"
            + "client_email = \"...@....iam.gserviceaccount.com\"\n"
            + "client_id = \"...\"\n"
            + "token_uri = \"https://oauth2.googleapis.com/token\"\n"
        )
        st.stop()

    if not LOG_SPREADSHEET_ID:
        st.warning("log_sheet_id가 설정되지 않아 조회 로그 기록을 비활성화합니다.")

_validate_runtime_config()

st.markdown(
    """
    <style>
      .block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 1100px; }
      .small-note { color: rgba(49,51,63,.65); font-size: 0.92rem; }
    
      
      /* ===== Top title size (-20%) & prevent clipping ===== */
      h1 {
        font-size: 1.8rem !important;
        line-height: 1.25 !important;
        padding-top: 0.15rem !important;
        margin-top: 0.20rem !important;
        overflow: visible !important;
      }
      @media (max-width: 640px){
        h1 {
          font-size: 1.55rem !important;
          line-height: 1.25 !important;
          padding-top: 0.20rem !important;
          margin-top: 0.25rem !important;
        }
      }
/* DataFrame row height compact */
      div[data-testid="stDataFrame"] .ag-row { height: 24px !important; }
      div[data-testid="stDataFrame"] .ag-cell { line-height: 22px !important; padding-top: 2px !important; padding-bottom: 2px !important; }
      div[data-testid="stDataFrame"] .ag-header-cell { padding-top: 2px !important; padding-bottom: 2px !important; }
      /* Fallback selectors (Streamlit versions) */
      .stDataFrame .ag-row { height: 24px !important; }
      .stDataFrame .ag-cell { line-height: 22px !important; padding-top: 2px !important; padding-bottom: 2px !important; }
      .stDataFrame .ag-header-cell { padding-top: 2px !important; padding-bottom: 2px !important; }

      


      /* ===== HTML rank table ===== */
      table.rank-table {
        margin-left: auto !important;
        margin-right: auto !important;
        border-collapse: collapse;
        width: 100%;
      }
      table.rank-table thead th {
        text-align: center !important;
        font-weight: 700;
        padding: 6px 8px;
        border-bottom: 1px solid rgba(49,51,63,.20);
        background: rgba(250,250,252,.90);
      }
      table.rank-table tbody td {
        text-align: center !important;
        padding: 6px 8px;
        border-bottom: 1px solid rgba(49,51,63,.12);
        white-space: nowrap;
      }
      
      /* ===== Summary compare table ===== */
      table.summary-table {
        margin-left: auto !important;
        margin-right: auto !important;
        border-collapse: collapse;
        width: 100%;
      }
      table.summary-table thead th {
        text-align: center !important;
        font-weight: 800;
        padding: 8px 10px;
        white-space: nowrap;
        border-bottom: 1px solid rgba(49,51,63,.20);
        background: #e5e7eb !important;
        color: #111 !important;
      }
      table.summary-table tbody th {
        text-align: center !important;
        font-weight: 700;
        padding: 8px 10px;
        border-bottom: 1px solid rgba(49,51,63,.12);
        background: rgba(250,250,252,.55);
      }
      table.summary-table tbody td {
        text-align: center !important;
        padding: 8px 10px;
        border-bottom: 1px solid rgba(49,51,63,.12);
        white-space: nowrap;
      }
      

      

      /* horizontal scroll wrapper for wide summary tables (mobile-safe) */
      .summary-wrap{
        width: 100%;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
      }
      table.summary-table thead th{
        white-space: nowrap;
      }
      @media (max-width: 640px){
        table.summary-table thead th{
          padding: 6px 6px;
          font-size: 0.82rem;
        }
        table.summary-table tbody th,
        table.summary-table tbody td{
          padding: 6px 6px;
          font-size: 0.82rem;
        }
      }
/* ===== Compare buttons sky-blue (secondary) ===== */
      button[data-testid="baseButton-secondary"] {
        background-color: #87CEEB !important;
        color: #08324a !important;
        border: 1px solid #5bb9d5 !important;
      }
      button[data-testid="baseButton-secondary"]:hover {
        background-color: #74c7e6 !important;
        border-color: #4fb3d4 !important;
        color: #08324a !important;
      }
      button[data-testid="baseButton-secondary"]:disabled {
        background-color: rgba(135,206,235,0.55) !important;
        color: rgba(8,50,74,0.65) !important;
        border-color: rgba(91,185,213,0.45) !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

YEAR_RE = re.compile(r"^\d{4}$")


def tight_height(n_rows: int) -> int:
    header = 34
    per_row = 26
    padding = 10
    return header + per_row * max(n_rows, 1) + padding


def render_rank_table_html(df_in: pd.DataFrame) -> None:
    """랭킹 표를 HTML 테이블로 렌더링(가운데 정렬 + 불필요한 빈 행 제거)."""
    df = df_in.copy()

    if "연도" in df.columns:
        df["연도"] = pd.to_numeric(df["연도"], errors="coerce").astype("Int64")

    if "공시가격(억)" in df.columns:
        s = pd.to_numeric(df["공시가격(억)"], errors="coerce")
        df["공시가격(억)"] = s.map(lambda x: f"{x:.2f}" if pd.notna(x) else "")

    # 표 출력 단계에서 최종 방어(완전 빈 행 제거)
    df = df.replace({"": pd.NA}).dropna(how="all").copy()

    html = df.to_html(index=False, classes="rank-table", escape=False)
    st.markdown(html, unsafe_allow_html=True)


# =========================
# Google Sheets Client (Secrets 기반)
# =========================
@st.cache_resource(show_spinner=False)

def render_compare_year_table_html(cmp: dict, last_year: str, sel_name: str, cmp_name: str) -> None:
    """선택/비교 대상의 2016 vs 최신연도(보통 2025) 가격/순위를 한눈에 보는 표로 표시.

    - 표 컬럼명을 '선택/비교' 같은 일반명 대신, 실제 물건명(구역/단지/동/층)으로 표시합니다.
    """
    y0 = int(cmp.get("year2016", 2016))
    y1 = int(last_year)

    sel_price_col = f"{sel_name} 가격(억)"
    sel_rank_col = f"{sel_name} 순위"
    cmp_price_col = f"{cmp_name} 가격(억)"
    cmp_rank_col = f"{cmp_name} 순위"

    df = pd.DataFrame(
        {
            sel_price_col: [cmp["base_price_2016"], cmp["base_price_last"]],
            sel_rank_col: [cmp["base_rank_2016"], cmp["base_rank_last"]],
            cmp_price_col: [cmp["cmp_price_2016"], cmp["cmp_price_last"]],
            cmp_rank_col: [cmp["cmp_rank_2016"], cmp["cmp_rank_last"]],
        },
        index=[y0, y1],
    )
    df.index.name = "연도"

    disp = df.copy()
    for c in [sel_price_col, cmp_price_col]:
        disp[c] = disp[c].map(lambda x: f"{float(x):.2f}")
    for c in [sel_rank_col, cmp_rank_col]:
        disp[c] = disp[c].map(lambda x: f"{int(x):,}")

    # 상단에 한 줄 요약(선택/비교 물건명)
    st.markdown(
        f"<div style='text-align:center; font-weight:700; margin:4px 0 10px 0;'>"
        f"선택: {sel_name} &nbsp;&nbsp;|&nbsp;&nbsp; 비교: {cmp_name}</div>",
        unsafe_allow_html=True,
    )

    html = disp.to_html(classes="summary-table", escape=False)
    st.markdown(html, unsafe_allow_html=True)

def get_gspread_client():
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    # 1) Streamlit Cloud 방식: secrets에 gcp_service_account가 있으면 그걸 사용
    if "gcp_service_account" in st.secrets:
        info = dict(st.secrets["gcp_service_account"])
        # Streamlit Secrets/TOML에서 private_key에 '\n'이 들어가는 경우가 많아 보정
        pk = info.get("private_key")
        if isinstance(pk, str):
            info["private_key"] = pk.replace("\\n", "\n")
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        return gspread.authorize(creds)

    # 2) 로컬/원본 방식: SERVICE_ACCOUNT_FILE 경로로 인증
    sa_path = str(st.secrets.get("SERVICE_ACCOUNT_FILE", "")).strip()
    if not sa_path:
        raise RuntimeError(
            "Google 인증 정보가 없습니다. Streamlit Secrets에 [gcp_service_account]를 넣거나 "
            "로컬 실행 시 SERVICE_ACCOUNT_FILE 경로를 지정해 주세요."
        )

    creds = Credentials.from_service_account_file(sa_path, scopes=scopes)
    return gspread.authorize(creds)


def open_worksheet_by_gid(sh, gid: int):
    ws = None
    for w in sh.worksheets():
        if int(w.id) == int(gid):
            ws = w
            break
    return ws if ws is not None else sh.sheet1


# =========================
# 유틸
# =========================
def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.replace({"": pd.NA, " ": pd.NA})

    # '주소' 컬럼을 내부 표준인 '구역'으로 통일
    if "구역" not in df.columns and "주소" in df.columns:
        df = df.rename(columns={"주소": "구역"})

    # 완전 빈 이름(_col*)으로 들어온 컬럼은 전부 NA인 경우에만 제거
    drop_cols = [c for c in df.columns if str(c).startswith("_col")]
    if drop_cols:
        drop_cols = [c for c in drop_cols if df[c].isna().all()]
        if drop_cols:
            df = df.drop(columns=drop_cols)

    return df
def _detect_year_cols(df: pd.DataFrame) -> list[str]:
    year_cols = []
    for c in df.columns:
        s = str(c).strip()
        if YEAR_RE.match(s):
            year_cols.append(s)
        else:
            try:
                f = float(s)
                if f.is_integer() and YEAR_RE.match(str(int(f))):
                    year_cols.append(str(int(f)))
            except Exception:
                pass
    return sorted(set(year_cols), key=lambda x: int(x))


def _coerce_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _filter_year_cols_with_data(df: pd.DataFrame, year_cols: list[str]) -> list[str]:
    keep = []
    for y in year_cols:
        s = pd.to_numeric(df[y], errors="coerce")
        if int(s.notna().sum()) > 0:
            keep.append(y)
    return keep


def _clean_main_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    df = df.iloc[:MAX_DATA_ROWS].copy()

    required = ["구역", "단지명", "동", "호"]
    for c in required:
        if c not in df.columns:
            raise ValueError(f"필수 컬럼이 없습니다: {c} (현재 컬럼: {list(df.columns)})")

    df["구역"] = df["구역"].astype(str).str.strip()
    df["단지명"] = df["단지명"].astype(str).str.strip()
    df["동"] = pd.to_numeric(df["동"], errors="coerce").astype("Int64")
    df["호"] = pd.to_numeric(df["호"], errors="coerce").astype("Int64")

    df = df.dropna(subset=["구역", "단지명", "동", "호"]).copy()
    df = df[(df["구역"].str.lower() != "nan") & (df["단지명"].str.lower() != "nan")].copy()
    return df


def _fmt_rank(rank, total) -> str:
    if pd.isna(rank) or pd.isna(total):
        return ""
    return f"{int(rank):,}/{int(total):,}"


def _parse_rank_text(s: str) -> int | None:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    txt = str(s).strip()
    if not txt:
        return None
    try:
        left = txt.split("/")[0].replace(",", "").strip()
        return int(left)
    except Exception:
        return None


def infer_floor_from_ho(ho: int) -> int | None:
    try:
        ho = int(ho)
    except Exception:
        return None
    if ho >= 100:
        return ho // 100
    return None


def unit_str_floor_only(zone: str, complex_name: str, dong: int, ho: int) -> str:
    floor = infer_floor_from_ho(ho)
    floor_txt = f"{floor}층" if floor is not None else "층?"
    return f"{zone} / {complex_name} / {dong}동 / {floor_txt}"



def _fmt_pyeong(pyeong_val) -> str:
    """평형 표시를 일관되게 '56평' 형태로 만듭니다."""
    if pyeong_val is None or (isinstance(pyeong_val, float) and pd.isna(pyeong_val)) or pd.isna(pyeong_val):
        return "-"
    s = str(pyeong_val).strip()
    if not s:
        return "-"
    # 이미 '평' 포함이면 그대로
    if "평" in s:
        return s
    # 숫자면 정수에 가깝게
    try:
        f = float(s)
        if abs(f - round(f)) < 1e-6:
            return f"{int(round(f))}평"
        return f"{f:.1f}평"
    except Exception:
        return f"{s}평"


def unit_str_pyeong_floor_only(zone: str, complex_name: str, pyeong_val, dong: int, ho: int) -> str:
    floor = infer_floor_from_ho(ho)
    floor_txt = f"{floor}층" if floor is not None else "층?"
    pyeong_txt = _fmt_pyeong(pyeong_val)
    return f"{zone} / {complex_name} / {pyeong_txt} / {dong}동 / {floor_txt}"
def detect_pyeong_col(df: pd.DataFrame) -> str | None:
    """평형 컬럼명을 유연하게 탐색합니다."""
    for c in ["평형", "평형(평)", "평", "평형_평", "평형평"]:
        if c in df.columns:
            return c
    return None


def get_pyeong_value(df_num: pd.DataFrame, zone: str, complex_name: str, dong: int, ho: int):
    """선택 키(구역/단지/동/호)에 해당하는 평형 값을 반환합니다."""
    pcol = detect_pyeong_col(df_num)
    if pcol is None:
        return pd.NA
    m = (
        (df_num["구역"] == zone)
        & (df_num["단지명"] == complex_name)
        & (df_num["동"] == dong)
        & (df_num["호"] == ho)
    )
    sub = df_num.loc[m, pcol]
    if sub.empty:
        return pd.NA
    return sub.iloc[0]


def legend_unit_label(zone: str, pyeong_val, dong: int, ho: int) -> str:
    """화살표 그래프 레전드용 라벨: 구역 + 평형 + 동/층"""
    floor = infer_floor_from_ho(ho)
    floor_txt = f"{floor}층" if floor is not None else "층?"
    return f"{zone} {_fmt_pyeong(pyeong_val)} {dong}동/{floor_txt}"

def infer_device_type() -> str:
    ua = ""
    try:
        ua = (st.context.headers or {}).get("User-Agent", "")  # type: ignore[attr-defined]
    except Exception:
        ua = ""

    ua_l = (ua or "").lower()
    mobile_keys = ["mobi", "android", "iphone", "ipad", "ipod", "windows phone"]
    return "mobile" if any(k in ua_l for k in mobile_keys) else "desktop"


def format_ho_for_log(ho: int) -> str:
    try:
        ho_i = int(ho)
    except Exception:
        return str(ho)
    return f"{ho_i}호" if ho_i >= 1000 else str(ho_i)


def append_lookup_log(zone: str, dong: int, ho: int, complex_name: str, event: str = "조회") -> None:
    # log_sheet_id가 없으면 로그 기록을 건너뜁니다.
    if not LOG_SPREADSHEET_ID:
        return
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    date_ymd = now.strftime("%Y-%m-%d")
    hhmm = now.strftime("%H:%M")
    device = infer_device_type()

    event_text = f"{event}:{complex_name}" if complex_name else event

    row = [
        date_ymd,
        hhmm,
        device,
        str(zone),
        str(int(dong)),
        format_ho_for_log(int(ho)),
        event_text,
    ]

    gc = get_gspread_client()
    sh = gc.open_by_key(LOG_SPREADSHEET_ID)
    ws = open_worksheet_by_gid(sh, LOG_GID)

    try:
        header = ws.row_values(1)
    except Exception:
        header = []

    expected_header = ["date_ymd", "time", "device", "zone", "dong", "ho", "event"]
    if [h.strip() for h in header] != expected_header:
        if not any(header):
            ws.update("A1:G1", [expected_header])

    ws.append_row(row, value_input_option="USER_ENTERED")


# =========================
# 구글시트 로딩 (헤더 2행)
# =========================
@st.cache_data(show_spinner=False, ttl=600)
def load_from_gsheet(spreadsheet_id: str, gid: int = 0, worksheet_name: str | None = None) -> pd.DataFrame:
    gc = get_gspread_client()
    sh = gc.open_by_key(spreadsheet_id)

    # 우선순위: worksheet_name(탭 이름) → gid
    ws = None
    if worksheet_name:
        try:
            ws = sh.worksheet(worksheet_name)
        except Exception:
            ws = None
    if ws is None:
        ws = open_worksheet_by_gid(sh, gid)

    values = ws.get_all_values()
    if not values:
        raise ValueError("시트에 데이터가 없습니다.")

    # 헤더(컬럼) 행 자동 탐지: '구역' 또는 '주소'를 모두 지원
    header_row_index = None
    must_have_sets = [
        {"구역", "단지명", "동", "호"},
        {"주소", "단지명", "동", "호"},  # 일부 시트에서 '구역' 대신 '주소' 사용
    ]

    for i, row in enumerate(values[:50]):  # 상단 50행 내에서 탐색
        cells = [str(x).strip() for x in row]
        s = set(cells)
        if any(ms.issubset(s) for ms in must_have_sets):
            header_row_index = i
            break

    # 그래도 못 찾으면: 1행을 헤더로 간주(데이터 1행을 헤더로 오인하지 않도록 2행 fallback 금지)
    if header_row_index is None:
        header_row_index = 0

    header = [str(x).strip() if str(x).strip() else f"_col{j}" for j, x in enumerate(values[header_row_index])]
    data = values[header_row_index + 1:]

    df = pd.DataFrame(data, columns=header)
    return _normalize_columns(df)
# =========================
# 랭킹 계산
# =========================
def compute_rank_tables(df_num: pd.DataFrame, year_cols: list[str], zone: str, complex_name: str, dong: int, ho: int):
    pick = df_num[
        (df_num["구역"] == zone)
        & (df_num["단지명"] == complex_name)
        & (df_num["동"] == dong)
        & (df_num["호"] == ho)
    ]
    if pick.empty:
        raise ValueError("선택한 조건의 행을 찾지 못했습니다.")
    pick_row = pick.iloc[0]

    zone_df = df_num[df_num["구역"] == zone].copy()
    all_df = df_num.copy()

    zone_n = int(zone_df.shape[0])
    all_n = int(all_df.shape[0])

    key_mask_zone = (zone_df["단지명"] == complex_name) & (zone_df["동"] == dong) & (zone_df["호"] == ho)
    key_mask_all = (all_df["구역"] == zone) & (all_df["단지명"] == complex_name) & (all_df["동"] == dong) & (all_df["호"] == ho)

    zone_rows, all_rows = [], []
    for y in year_cols:
        zone_rank_series = zone_df[y].rank(method="min", ascending=False)
        all_rank_series = all_df[y].rank(method="min", ascending=False)

        zr = zone_rank_series[key_mask_zone]
        ar = all_rank_series[key_mask_all]

        price = pd.to_numeric(pick_row.get(y, pd.NA), errors="coerce")
        if pd.isna(price):
            continue  # 데이터 없는 연도는 행을 생성하지 않음
        zone_rank = zr.iloc[0] if (len(zr) and pd.notna(zr.iloc[0])) else pd.NA
        all_rank = ar.iloc[0] if (len(ar) and pd.notna(ar.iloc[0])) else pd.NA

        zone_rows.append({"연도": int(y), "공시가격(억)": price, "구역 내 랭킹": _fmt_rank(zone_rank, zone_n)})
        all_rows.append({"연도": int(y), "공시가격(억)": price, "압구정 전체 랭킹": _fmt_rank(all_rank, all_n)})

    zone_table = pd.DataFrame(zone_rows)
    all_table = pd.DataFrame(all_rows)

    zone_table = zone_table.dropna(subset=["공시가격(억)"]).copy()
    zone_table = zone_table[zone_table["구역 내 랭킹"].astype(str).str.strip() != ""].copy()

    all_table = all_table.dropna(subset=["공시가격(억)"]).copy()
    all_table = all_table[all_table["압구정 전체 랭킹"].astype(str).str.strip() != ""].copy()

    return zone_table, all_table


# =========================
# 비교대상(타구역) 선정: 2016 가격 가장 유사
# =========================
def find_closest_by_2016(df_num: pd.DataFrame, base_zone: str, base_key: tuple, year2016: str = "2016"):
    if year2016 not in df_num.columns:
        return None

    sel_zone, sel_complex, sel_dong, sel_ho = base_key
    base_row = df_num[
        (df_num["구역"] == sel_zone)
        & (df_num["단지명"] == sel_complex)
        & (df_num["동"] == sel_dong)
        & (df_num["호"] == sel_ho)
    ]
    if base_row.empty:
        return None

    base_price = pd.to_numeric(base_row.iloc[0][year2016], errors="coerce")
    if pd.isna(base_price):
        return None

    cand = df_num.copy()
    cand = cand[cand["구역"] != base_zone].copy()
    cand["p2016"] = pd.to_numeric(cand[year2016], errors="coerce")
    cand = cand.dropna(subset=["p2016"]).copy()
    if cand.empty:
        return None

    cand["diff"] = (cand["p2016"] - base_price).abs()
    best = cand.sort_values(["diff", "구역", "단지명", "동", "호"]).iloc[0]

    return {
        "base_price": float(base_price),
        "cmp_zone": str(best["구역"]),
        "cmp_complex": str(best["단지명"]),
        "cmp_dong": int(best["동"]),
        "cmp_ho": int(best["호"]),
        "cmp_price": float(best["p2016"]),
        "diff": float(best["diff"]),
    }



def find_candidates_by_2016_with_rank_inversion(
    df_num: pd.DataFrame,
    base_zone: str,
    base_key: tuple,
    year2016: str = "2016",
    last_year: str = "2025",
    require_inversion: bool = True,
) -> pd.DataFrame:
    """(타구역) 2016 유사 + 순위 역전 후보들을 계산하여 DataFrame으로 반환합니다.

    반환 DataFrame 컬럼(주요):
      - cmp_zone, cmp_complex, cmp_dong, cmp_ho
      - diff_price_2016 (2016 가격 차이, 절대값)
      - relative_rank_swing (상대 순위차 변화량: |(base-cand)_last - (base-cand)_2016|)
      - cmp_price_2016, cmp_rank_2016, cmp_price_last, cmp_rank_last
      - base_price_2016, base_rank_2016, base_price_last, base_rank_last
    """
    if year2016 not in df_num.columns or last_year not in df_num.columns:
        return pd.DataFrame()

    sel_zone, sel_complex, sel_dong, sel_ho = base_key
    base_row = df_num[
        (df_num["구역"] == sel_zone)
        & (df_num["단지명"] == sel_complex)
        & (df_num["동"] == sel_dong)
        & (df_num["호"] == sel_ho)
    ]
    if base_row.empty:
        return pd.DataFrame()

    base_idx = base_row.index[0]
    base_p2016 = pd.to_numeric(base_row.iloc[0].get(year2016, pd.NA), errors="coerce")
    base_plast = pd.to_numeric(base_row.iloc[0].get(last_year, pd.NA), errors="coerce")
    if pd.isna(base_p2016) or pd.isna(base_plast):
        return pd.DataFrame()

    all_df = df_num.copy()
    # 평형 컬럼 탐색(있으면 후보 리스트 표시에 활용)
    pyeong_col = None
    for _c in ["평형", "평형(평)", "평", "평형_평", "평형평"]:
        if _c in all_df.columns:
            pyeong_col = _c
            break
    r2016 = all_df[year2016].rank(method="min", ascending=False)
    rlast = all_df[last_year].rank(method="min", ascending=False)

    base_r2016 = r2016.loc[base_idx]
    base_rlast = rlast.loc[base_idx]
    if pd.isna(base_r2016) or pd.isna(base_rlast):
        return pd.DataFrame()

    cand = all_df[all_df["구역"] != base_zone].copy()
    cand["p2016"] = pd.to_numeric(cand.get(year2016), errors="coerce")
    cand["plast"] = pd.to_numeric(cand.get(last_year), errors="coerce")
    cand["r2016"] = r2016.loc[cand.index]
    cand["rlast"] = rlast.loc[cand.index]
    cand = cand.dropna(subset=["p2016", "plast", "r2016", "rlast"]).copy()
    if cand.empty:
        return pd.DataFrame()

    diff_2016 = base_r2016 - cand["r2016"]
    diff_last = base_rlast - cand["rlast"]

    # 역전 여부: 2016과 last_year 사이에 (선택-후보) 상대 순위차의 부호가 뒤집힘
    cand["is_inversion"] = ((diff_2016 != 0) & (diff_last != 0) & ((diff_2016 * diff_last) < 0)).astype(int)

    if require_inversion:
        cand = cand[cand["is_inversion"] == 1].copy()
        if cand.empty:
            return pd.DataFrame()

    cand["diff_price_2016"] = (cand["p2016"] - base_p2016).abs()
    cand["cand_rank_change_abs"] = (cand["rlast"] - cand["r2016"]).abs()
    cand["relative_rank_swing"] = (diff_last - diff_2016).abs()

    cand_out = pd.DataFrame(
        {
            "year2016": year2016,
            "last_year": last_year,
            "base_price_2016": float(base_p2016),
            "base_rank_2016": float(base_r2016),
            "base_price_last": float(base_plast),
            "base_rank_last": float(base_rlast),
            "base_rank_change_abs": float(abs(base_rlast - base_r2016)),
            "cmp_zone": cand["구역"].astype(str),
            "cmp_complex": cand["단지명"].astype(str),
            "cmp_dong": cand["동"].astype(int),
            "cmp_ho": cand["호"].astype(int),
            "cmp_pyeong": (cand[pyeong_col] if pyeong_col is not None else pd.NA),
            "cmp_price_2016": cand["p2016"].astype(float),
            "cmp_rank_2016": cand["r2016"].astype(float),
            "cmp_price_last": cand["plast"].astype(float),
            "cmp_rank_last": cand["rlast"].astype(float),
            "is_inversion": cand["is_inversion"].astype(int),
            "diff_price_2016": cand["diff_price_2016"].astype(float),
            "cand_rank_change_abs": cand["cand_rank_change_abs"].astype(float),
            "relative_rank_swing": cand["relative_rank_swing"].astype(float),
        }
    )

    # 정렬: 2016 유사(가까움) 우선 + 같은 유사도에서는 상대변동 큰 후보를 위로
    cand_out = cand_out.sort_values(
        ["diff_price_2016", "relative_rank_swing", "cand_rank_change_abs", "cmp_zone", "cmp_complex", "cmp_dong", "cmp_ho"],
        ascending=[True, False, False, True, True, True, True],
    ).reset_index(drop=True)

    return cand_out


def find_closest_by_2016_with_rank_inversion(
    df_num: pd.DataFrame,
    base_zone: str,
    base_key: tuple,
    year2016: str = "2016",
    last_year: str = "2025",
    top_n_closest: int = 80,
):
    """2016 유사 + 순위 역전 후보 중 '상대변동 최대' 1개를 선택해 dict로 반환합니다.

    선택 규칙:
      1) 역전 후보 전체를 계산
      2) 2016 가격이 가까운 상위 top_n_closest 후보로 제한
      3) 그 안에서 relative_rank_swing(상대 순위차 변화량) 최대를 선택
    """
    cand = find_candidates_by_2016_with_rank_inversion(
        df_num=df_num,
        base_zone=base_zone,
        base_key=base_key,
        year2016=year2016,
        last_year=last_year,
    )
    if cand.empty:
        return None

    top_n = max(1, int(top_n_closest))
    cand_top = cand.head(top_n) if len(cand) > top_n else cand

    best = cand_top.sort_values(
        ["relative_rank_swing", "cand_rank_change_abs", "diff_price_2016"],
        ascending=[False, False, True],
    ).iloc[0]

    return {
        "year2016": best["year2016"],
        "last_year": best["last_year"],

        "base_price_2016": float(best["base_price_2016"]),
        "base_rank_2016": int(best["base_rank_2016"]),
        "base_price_last": float(best["base_price_last"]),
        "base_rank_last": int(best["base_rank_last"]),
        "base_rank_change_abs": float(best["base_rank_change_abs"]),

        "cmp_zone": str(best["cmp_zone"]),
        "cmp_complex": str(best["cmp_complex"]),
        "cmp_dong": int(best["cmp_dong"]),
        "cmp_ho": int(best["cmp_ho"]),
        "cmp_price_2016": float(best["cmp_price_2016"]),
        "cmp_rank_2016": int(best["cmp_rank_2016"]),
        "cmp_price_last": float(best["cmp_price_last"]),
        "cmp_rank_last": int(best["cmp_rank_last"]),
        "cand_rank_change_abs": float(best["cand_rank_change_abs"]),

        "diff_price_2016": float(best["diff_price_2016"]),
        "relative_rank_swing": float(best["relative_rank_swing"]),
    }
def build_price_series(df_num: pd.DataFrame, year_cols: list[str], zone: str, complex_name: str, dong: int, ho: int):
    row = df_num[
        (df_num["구역"] == zone)
        & (df_num["단지명"] == complex_name)
        & (df_num["동"] == dong)
        & (df_num["호"] == ho)
    ]
    if row.empty:
        return [], []
    r = row.iloc[0]
    years, prices = [], []
    for y in year_cols:
        v = pd.to_numeric(r.get(y, pd.NA), errors="coerce")
        if pd.notna(v):
            years.append(int(y))
            prices.append(float(v))
    return years, prices


# =========================
# 차트
# =========================
def plot_rank_line(years: list[int], ranks: list[int], title: str, style: dict):
    fig, ax = plt.subplots(figsize=(7.0, RANK_FIG_HEIGHT_IN), dpi=RANK_FIG_DPI)

    ax.plot(
        years, ranks,
        color=style["line_color"],
        linewidth=style["line_width"],
        linestyle=style["line_style"],
        marker=style["marker"],
        markersize=style["marker_size"],
        markerfacecolor=style["marker_face"],
        markeredgecolor=style["marker_edge"],
        markeredgewidth=style["marker_edge_width"],
    )

    ax.set_title(title)
    ax.set_xlabel("연도")
    ax.set_ylabel("순위 (작을수록 상위)")
    ax.set_xticks(years)
    ax.set_xticklabels([str(y) for y in years], rotation=0)
    ax.invert_yaxis()

    if SHOW_RANK_LABELS:
        for x, y in zip(years, ranks):
            ax.annotate(
                f"{y}",
                xy=(x, y),
                xytext=(0, RANK_LABEL_Y_OFFSET),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=RANK_LABEL_FONTSIZE,
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="none", alpha=0.9),
            )

    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def plot_price_compare(years: list[int], sel_prices: list[float], cmp_prices: list[float],
                       sel_label: str, cmp_label: str):
    fig, ax = plt.subplots(figsize=(7.0, RANK_FIG_HEIGHT_IN), dpi=RANK_FIG_DPI)

    ax.plot(
        years, sel_prices,
        color=SEL_PRICE_STYLE["line_color"],
        linewidth=SEL_PRICE_STYLE["line_width"],
        linestyle=SEL_PRICE_STYLE["line_style"],
        marker=SEL_PRICE_STYLE["marker"],
        markersize=SEL_PRICE_STYLE["marker_size"],
        markerfacecolor=SEL_PRICE_STYLE["marker_face"],
        markeredgecolor=SEL_PRICE_STYLE["marker_edge"],
        markeredgewidth=SEL_PRICE_STYLE["marker_edge_width"],
        label=sel_label,
    )
    ax.plot(
        years, cmp_prices,
        color=CMP_PRICE_STYLE["line_color"],
        linewidth=CMP_PRICE_STYLE["line_width"],
        linestyle=CMP_PRICE_STYLE["line_style"],
        marker=CMP_PRICE_STYLE["marker"],
        markersize=CMP_PRICE_STYLE["marker_size"],
        markerfacecolor=CMP_PRICE_STYLE["marker_face"],
        markeredgecolor=CMP_PRICE_STYLE["marker_edge"],
        markeredgewidth=CMP_PRICE_STYLE["marker_edge_width"],
        label=cmp_label,
    )

    ax.set_title("2016 유사 가격 타구역 비교: 공시가격 추이")
    ax.set_xlabel("연도")
    ax.set_ylabel("공시가격(억)")

    ax.set_xticks(years)
    ax.set_xticklabels([str(y) for y in years], rotation=0)

    # 마지막 연도만 볼드 라벨
    last_year = years[-1]
    sel_last = sel_prices[-1]
    cmp_last = cmp_prices[-1]

    spread = abs(sel_last - cmp_last)
    sel_off = (0, 16)
    cmp_off = (0, -26) if spread < 1.0 else (0, 16)

    ax.annotate(
        f"{sel_last:.2f}",
        xy=(last_year, sel_last),
        xytext=sel_off,
        textcoords="offset points",
        ha="center",
        va="bottom" if sel_off[1] >= 0 else "top",
        fontsize=11,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="none", alpha=0.9),
    )
    ax.annotate(
        f"{cmp_last:.2f}",
        xy=(last_year, cmp_last),
        xytext=cmp_off,
        textcoords="offset points",
        ha="center",
        va="bottom" if cmp_off[1] >= 0 else "top",
        fontsize=11,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="none", alpha=0.9),
    )

    ax.grid(True, alpha=0.3)
    leg = ax.legend(loc="best")
    # 범례/축/제목 등 모든 텍스트에 얇은 검정 엣지 적용
    for _t in [ax.title, ax.xaxis.label, ax.yaxis.label]:
        _t.set_path_effects([pe.withStroke(linewidth=0.3, foreground="black")])
    for _lab in (ax.get_xticklabels() + ax.get_yticklabels()):
        _lab.set_path_effects([pe.withStroke(linewidth=0.3, foreground="black")])
    if leg is not None:
        for _lt in leg.get_texts():
                            _lt.set_fontweight("normal")
                            _lt.set_path_effects([pe.withStroke(linewidth=0.3, foreground="black")])
    fig.tight_layout()
    return fig

def plot_price_compare_bars(
    years: list[int],
    sel_prices: list[float],
    cmp_prices: list[float],
    sel_label: str,
    cmp_label: str,
    title: str,
):
    """연도별 2개 시리즈(선택/비교)를 그룹 막대로 표시."""
    import numpy as np

    fig, ax = plt.subplots(figsize=(7.4, RANK_FIG_HEIGHT_IN), dpi=RANK_FIG_DPI)

    x = np.arange(len(years))
    width = 0.40

    b1 = ax.bar(
        x - width / 2,
        sel_prices,
        width,
        label=sel_label,
        color=SEL_BAR_STYLE["face_color"],
        edgecolor=SEL_BAR_STYLE["edge_color"],
        linewidth=SEL_BAR_STYLE["linewidth"],
        alpha=SEL_BAR_STYLE["alpha"],
        hatch=SEL_BAR_STYLE["hatch"],
        zorder=3,
    )
    b2 = ax.bar(
        x + width / 2,
        cmp_prices,
        width,
        label=cmp_label,
        color=CMP_BAR_STYLE["face_color"],
        edgecolor=CMP_BAR_STYLE["edge_color"],
        linewidth=CMP_BAR_STYLE["linewidth"],
        alpha=CMP_BAR_STYLE["alpha"],
        hatch=CMP_BAR_STYLE["hatch"],
        zorder=3,
    )

    ax.set_title(title)
    ax.set_xlabel("연도")
    ax.set_ylabel("공시가격(억)")
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in years], rotation=0)

    # 값 라벨(과밀 방지를 위해 모든 연도에 작은 라벨 적용)
    def _label_bars(bars, values):
        for rect, v in zip(bars, values):
            if v is None:
                continue
            ax.annotate(
                f"{v:.2f}",
                (rect.get_x() + rect.get_width() / 2, rect.get_height()),
                textcoords="offset points",
                xytext=(0, 6),
                ha="center",
                va="bottom",
                fontsize=8,
                fontweight="bold" if rect is bars[-1] else "normal",
            )

    _label_bars(b1, sel_prices)
    _label_bars(b2, cmp_prices)

    ax.grid(True, axis="y", alpha=0.25, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(loc="best", frameon=True, framealpha=0.9)
    fig.tight_layout()
    return fig
# =========================
# 메인
# =========================
st.title("압구정 예비 권리가액 랭킹")
st.caption(APP_DESCRIPTION)
st.markdown(PROMO_TEXT_HTML, unsafe_allow_html=True)

try:
    df_raw = load_from_gsheet(MAIN_SPREADSHEET_ID, MAIN_GID, MAIN_WORKSHEET_NAME)
except Exception as e:
    st.error(f"구글시트 로딩 실패: {e}")
    st.stop()

try:
    df = _clean_main_df(df_raw)
except Exception as e:
    st.error(f"데이터 정리 실패: {e}")
    st.stop()

year_cols_all = _detect_year_cols(df)
df_num = _coerce_numeric(df, year_cols_all)
year_cols = _filter_year_cols_with_data(df_num, year_cols_all)
# 요청: 공시가격은 2016년부터 사용
year_cols = [y for y in year_cols if int(y) >= 2016]
if not year_cols:
    st.error("연도 컬럼은 있으나 실제 데이터가 있는 연도가 없습니다.")
    st.stop()

zones = sorted(df_num["구역"].dropna().unique().tolist())



def plot_price_rank_arrow(
    base_p0: float, base_r0: float, base_p1: float, base_r1: float,
    cmp_p0: float, cmp_r0: float, cmp_p1: float, cmp_r1: float,
    last_year: str,
    sel_label: str, cmp_label: str,
):
    """2016→최신연도 이동을 '가격(x) - 순위(y)' 공간에서 화살표로 표현.

    라벨(연도/가격/순위) 박스가 겹치는 경우가 자주 발생하므로,
    - 2016 라벨끼리, 2025 라벨끼리 각각 근접하면 서로 다른 오프셋을 자동 부여하여 겹침을 최소화합니다.
    """
    fig, ax = plt.subplots(figsize=(7.2, 4.8), dpi=RANK_FIG_DPI)
    ax.invert_yaxis()  # 위로 갈수록 상위(작은 순위)

    def _pt_label(year: str, price: float, rank: float) -> str:
        return f"{year}\n{price:.2f}억\n{int(rank):,}위"

    def _separate_offsets(p_a, r_a, p_b, r_b, default_a, default_b):
        """두 점이 근접하면 라벨 오프셋을 다르게 주어 겹침을 피한다(포인트 단위)."""
        close = (abs(p_a - p_b) < 2.0) and (abs(r_a - r_b) < 250.0)
        if not close:
            return default_a, default_b

        # 더 상위(작은 순위)인 쪽 라벨을 위로, 다른 쪽은 아래로 크게 분리
        if r_a <= r_b:
            return (12, -66), (12, 18)
        else:
            return (12, 18), (12, -66)

    # 기본 오프셋(겹치지 않으면 그대로 사용)
    base0_off, cmp0_off = _separate_offsets(
        base_p0, base_r0, cmp_p0, cmp_r0,
        default_a=(12, -18),
        default_b=(12, 18),
    )
    base1_off, cmp1_off = _separate_offsets(
        base_p1, base_r1, cmp_p1, cmp_r1,
        default_a=(12, -18),
        default_b=(12, 18),
    )

    # 점/화살표(선택)
    ax.scatter(
        [base_p0, base_p1], [base_r0, base_r1],
        s=110, marker='o',
        c=SEL_BAR_STYLE['face_color'],
        edgecolors=SEL_BAR_STYLE['edge_color'],
        linewidths=SEL_BAR_STYLE['linewidth'],
        zorder=3,
        label=sel_label,
    )
    ax.annotate(
        '', xy=(base_p1, base_r1), xytext=(base_p0, base_r0),
        arrowprops=dict(arrowstyle='->', lw=2.6, color=SEL_BAR_STYLE['edge_color']),
        zorder=2,
    )

    # 점/화살표(비교)
    ax.scatter(
        [cmp_p0, cmp_p1], [cmp_r0, cmp_r1],
        s=110, marker='s',
        c=CMP_BAR_STYLE['face_color'],
        edgecolors=CMP_BAR_STYLE['edge_color'],
        linewidths=CMP_BAR_STYLE['linewidth'],
        zorder=3,
        label=cmp_label,
    )
    ax.annotate(
        '', xy=(cmp_p1, cmp_r1), xytext=(cmp_p0, cmp_r0),
        arrowprops=dict(arrowstyle='->', lw=2.6, color=CMP_BAR_STYLE['edge_color']),
        zorder=2,
    )

    # 라벨(연도/가격/순위) - 겹침 최소화 오프셋 적용
    ax.annotate(
        _pt_label("2016", base_p0, base_r0),
        xy=(base_p0, base_r0),
        xytext=base0_off,
        textcoords="offset points",
        fontsize=10,
        fontweight="bold",
        color=SEL_BAR_STYLE["edge_color"],
        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=SEL_BAR_STYLE["edge_color"], alpha=0.78),
        zorder=4,
    )
    ax.annotate(
        _pt_label(str(last_year), base_p1, base_r1),
        xy=(base_p1, base_r1),
        xytext=base1_off,
        textcoords="offset points",
        fontsize=10,
        fontweight="bold",
        color=SEL_BAR_STYLE["edge_color"],
        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=SEL_BAR_STYLE["edge_color"], alpha=0.78),
        zorder=4,
    )
    ax.annotate(
        _pt_label("2016", cmp_p0, cmp_r0),
        xy=(cmp_p0, cmp_r0),
        xytext=cmp0_off,
        textcoords="offset points",
        fontsize=10,
        fontweight="bold",
        color=CMP_BAR_STYLE["edge_color"],
        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=CMP_BAR_STYLE["edge_color"], alpha=0.78),
        zorder=4,
    )
    ax.annotate(
        _pt_label(str(last_year), cmp_p1, cmp_r1),
        xy=(cmp_p1, cmp_r1),
        xytext=cmp1_off,
        textcoords="offset points",
        fontsize=10,
        fontweight="bold",
        color=CMP_BAR_STYLE["edge_color"],
        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=CMP_BAR_STYLE["edge_color"], alpha=0.78),
        zorder=4,
    )

    ax.set_title(f"가격-순위 이동(2016→{last_year})")
    ax.set_xlabel("공시가격(억)")
    ax.set_ylabel("압구정 전체 순위(위로 갈수록 상위)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc='best')
    fig.tight_layout()
    return fig
def reset_after_zone():
    st.session_state["dong_pair"] = None
    st.session_state["ho"] = None
    st.session_state["confirmed"] = False
    st.session_state["cmp_pick_key"] = None


def reset_after_dong():
    st.session_state["ho"] = None
    st.session_state["confirmed"] = False
    st.session_state["cmp_pick_key"] = None


st.session_state.setdefault("zone", None)
st.session_state.setdefault("dong_pair", None)
st.session_state.setdefault("ho", None)
st.session_state.setdefault("confirmed", False)
st.session_state.setdefault("cmp_pick_key", None)

zone = st.selectbox("구역 선택", zones, index=None, placeholder="구역을 선택하세요",
                    key="zone", on_change=reset_after_zone)

if zone is None:
    dong_pairs = []
    _dong_is_unique = True
else:
    zone_df0 = df_num[df_num["구역"] == zone].copy()
    dong_pairs = (
        zone_df0[["단지명", "동"]]
        .dropna()
        .drop_duplicates()
        .sort_values(["단지명", "동"])
        .to_records(index=False)
        .tolist()
    )

    # 같은 구역 내에서 '동' 값이 단지명과 1:1이면, 화면에는 '동'만 노출(요청사항: 구역/동/호)
    # 만약 같은 '동'이 여러 단지에 존재하면 혼동 방지를 위해 단지명도 함께 표기합니다.
    _dong_only_ok = (pd.Series([int(x[1]) for x in dong_pairs]).value_counts().max() == 1) if dong_pairs else True
    _dong_is_unique = bool(_dong_only_ok)


def fmt_dong(x):
    cn, d = x
    return f"{int(d)}동" if _dong_is_unique else f"{cn} / {int(d)}동"


dong_pair = st.selectbox(
    "동 선택",
    dong_pairs,
    index=None,
    placeholder="동을 선택하세요",
    key="dong_pair",
    format_func=fmt_dong,
    disabled=(zone is None),
    on_change=reset_after_dong if zone is not None else None,
)

if zone is None or dong_pair is None:
    ho_list = []
else:
    complex_name0, dong0 = dong_pair[0], int(dong_pair[1])
    ho_list = (
        df_num[(df_num["구역"] == zone) & (df_num["단지명"] == complex_name0) & (df_num["동"] == dong0)]["호"]
        .dropna()
        .drop_duplicates()
        .sort_values()
        .astype(int)
        .tolist()
    )

ho = st.selectbox("호 선택", ho_list, index=None, placeholder="호를 선택하세요",
                  key="ho", disabled=(dong_pair is None))

confirmed_click = st.button("확인", use_container_width=True)

if confirmed_click:
    if st.session_state["zone"] is None or st.session_state["dong_pair"] is None or st.session_state["ho"] is None:
        st.warning("구역, 동, 호를 모두 선택한 후 확인을 눌러주세요.")
        st.session_state["confirmed"] = False
    else:
        st.session_state["confirmed"] = True

        # ✅ 조회 로그 기록 (실패해도 앱은 계속 동작)
        try:
            _zone = st.session_state["zone"]
            _complex, _dong = st.session_state["dong_pair"][0], int(st.session_state["dong_pair"][1])
            _ho = int(st.session_state["ho"])
            append_lookup_log(zone=_zone, dong=_dong, ho=_ho, complex_name=_complex, event="조회")
        except Exception as e:
            st.warning(f"조회 로그 기록 실패(권한/시트 설정 확인 필요): {e}")

if not st.session_state.get("confirmed", False):
    st.markdown('<div class="small-note">구역 → 동 → 호 선택 후, 확인을 누르면 결과가 표시됩니다.</div>',
                unsafe_allow_html=True)
    st.stop()

zone = st.session_state["zone"]
complex_name, dong = st.session_state["dong_pair"][0], int(st.session_state["dong_pair"][1])
ho = int(st.session_state["ho"])


try:
    zone_table, all_table = compute_rank_tables(df_num, year_cols, zone, complex_name, dong, ho)
except Exception as e:
    st.error(f"랭킹 산출 실패: {e}")
    st.stop()


# =========================
# 선택 요약 (요청: 한 줄 요약)
# =========================
# 선택 행
pick = df_num[
    (df_num["구역"] == zone)
    & (df_num["단지명"] == complex_name)
    & (df_num["동"] == dong)
    & (df_num["호"] == ho)
]
pick_row = pick.iloc[0] if not pick.empty else None

def _find_first_col(df_: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = set(df_.columns)
    for c in candidates:
        if c in cols:
            return c
    return None

area_col = _find_first_col(df_num, ["전용면적(㎡)", "전용면적", "전용면적  (㎡).", "전용면적 (㎡)", "전용면적㎡"])
land_col = _find_first_col(df_num, ["대지지분(평)", "대지지분", "대지지분    (평)", "대지지분 (평)", "대지지분평"])
note_col = _find_first_col(df_num, ["특기사항", "특기 사항", "비고", "Remarks"])

def _fmt_num(v, fmt: str = "{:.2f}") -> str:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
            return "-"
    except Exception:
        pass
    try:
        return fmt.format(float(v))
    except Exception:
        return "-"

# 2025 요약값
_y = 2025
price_2025 = zone_table.loc[zone_table["연도"] == _y, "공시가격(억)"]
price_2025_v = price_2025.iloc[0] if len(price_2025) else pd.NA

zone_rank_2025 = zone_table.loc[zone_table["연도"] == _y, "구역 내 랭킹"]
zone_rank_2025_v = str(zone_rank_2025.iloc[0]) if len(zone_rank_2025) else "-"

all_rank_2025 = all_table.loc[all_table["연도"] == _y, "압구정 전체 랭킹"]
all_rank_2025_v = str(all_rank_2025.iloc[0]) if len(all_rank_2025) else "-"

area_v = pd.to_numeric(pick_row[area_col], errors="coerce") if (pick_row is not None and area_col) else pd.NA
land_v = pd.to_numeric(pick_row[land_col], errors="coerce") if (pick_row is not None and land_col) else pd.NA
note_v = pick_row[note_col] if (pick_row is not None and note_col) else None

st.subheader("선택 요약")
st.caption(f"선택: {zone} / {dong}동 / {ho}호")
note_text = ""
try:
    if note_v is not None and not pd.isna(note_v):
        _s = str(note_v).strip()
        if _s and _s.lower() != "nan":
            note_text = re.sub(r"\s+", " ", _s)
except Exception:
    note_text = ""

extra_note = f" / **특기사항** {note_text}" if note_text else ""

st.markdown(
    f"**2025 공시가격** {_fmt_num(price_2025_v, '{:.2f}')}(억) / "
    f"**구역내 순위** {zone_rank_2025_v} / "
    f"**압구정 전체순위** {all_rank_2025_v} / "
    f"**전용면적** {_fmt_num(area_v, '{:.2f}')} (㎡) / "
    f"**대지지분** {_fmt_num(land_v, '{:.2f}')} (평)"
    f"{extra_note}"
)


st.divider()


# =========================
# 하단 표/그래프 레이아웃 (요청 반영)
#   1행: (좌) 구역 내 연도별 랭킹 표  | (우) 구역 내 순위변화 그래프
#   2행: (좌) 압구정 전체 연도별 랭킹 표 | (우) 압구정 전체 순위변화 그래프
#   3행: 유사 타구역 비교 그래프 (전체 폭)
# =========================

# 랭킹 그래프용 데이터 준비
z_plot = zone_table.copy()
z_plot["rank"] = z_plot["구역 내 랭킹"].apply(_parse_rank_text)
z_plot = z_plot.dropna(subset=["rank"]).copy()
z_plot["연도"] = z_plot["연도"].astype(int)
z_plot["rank"] = z_plot["rank"].astype(int)
z_plot = z_plot.sort_values("연도")

a_plot = all_table.copy()
a_plot["rank"] = a_plot["압구정 전체 랭킹"].apply(_parse_rank_text)
a_plot = a_plot.dropna(subset=["rank"]).copy()
a_plot["연도"] = a_plot["연도"].astype(int)
a_plot["rank"] = a_plot["rank"].astype(int)
a_plot = a_plot.sort_values("연도")

st.subheader("랭킹변화")

# ---------- 1행 ----------
l1, r1 = st.columns(2, gap="large")
with l1:
    st.markdown("**구역 내 연도별 랭킹**")
    render_rank_table_html(zone_table)

with r1:
    st.markdown("**구역 내 순위 변화(연도별)**")
    if z_plot.empty:
        st.info("구역 내 순위 그래프를 그릴 데이터가 없습니다.")
    else:
        fig1 = plot_rank_line(
            years=z_plot["연도"].tolist(),
            ranks=z_plot["rank"].tolist(),
            title=f"{zone} / {dong}동 / {ho}호  (구역 내 순위)",
            style=ZONE_RANK_STYLE,
        )
        st.pyplot(fig1, use_container_width=True)

# ---------- 2행 ----------
l2, r2 = st.columns(2, gap="large")
with l2:
    st.markdown("**압구정 전체 연도별 랭킹**")
    render_rank_table_html(all_table)

with r2:
    st.markdown("**압구정 전체 순위 변화(연도별)**")
    if a_plot.empty:
        st.info("압구정 전체 순위 그래프를 그릴 데이터가 없습니다.")
    else:
        fig2 = plot_rank_line(
            years=a_plot["연도"].tolist(),
            ranks=a_plot["rank"].tolist(),
            title=f"{zone} / {dong}동 / {ho}호  (압구정 전체 순위)",
            style=ALL_RANK_STYLE,
        )
        st.pyplot(fig2, use_container_width=True)

st.divider()

st.markdown("**3) 타구역 비교 (기준단지 1개 + 비교단지 2개 선택 → 비교하기)**")

last_year = str(max(int(y) for y in year_cols))

pyeong_col = detect_pyeong_col(df_num)
if pyeong_col is None:
    st.info("평형 컬럼(예: '평형' 또는 '평형(평)')이 없어 3번 비교 기능을 사용할 수 없습니다.")
else:
    # --- 공통: 전체 순위(2016/최신연도) 시리즈를 미리 계산 ---
    if "2016" not in df_num.columns or last_year not in df_num.columns:
        st.info("2016 또는 최신연도 컬럼이 없어 3번 비교 기능을 사용할 수 없습니다.")
    else:
        r2016_all = df_num["2016"].rank(method="min", ascending=False)
        rlast_all = df_num[last_year].rank(method="min", ascending=False)

        def _pyeong_sort_key(s: str):
            # '56평' / '56.5평' / '56' 등 대응
            import re
            m = re.search(r"(\d+(?:\.\d+)?)", str(s))
            return float(m.group(1)) if m else 999999.0

        def _get_pyeong_options(_zone: str, _complex: str) -> list[str]:
            sub = df_num[(df_num["구역"] == _zone) & (df_num["단지명"] == _complex)]
            if sub.empty:
                return []
            vals = sub[pyeong_col].apply(_fmt_pyeong).dropna().astype(str).unique().tolist()
            vals = [v for v in vals if str(v).strip() and str(v).strip().lower() != "nan"]
            vals = sorted(set(vals), key=_pyeong_sort_key)
            return vals

        def _pick_representative(_zone: str, _complex: str, _pyeong_fmt: str):
            """(구역/단지/평형) 중 최신연도 공시가격이 가장 높은 1개 동/호를 대표로 선택."""
            sub = df_num[(df_num["구역"] == _zone) & (df_num["단지명"] == _complex)].copy()
            if sub.empty:
                return None

            sub["_pyeong_fmt"] = sub[pyeong_col].apply(_fmt_pyeong)
            sub = sub[sub["_pyeong_fmt"] == _pyeong_fmt].copy()
            if sub.empty:
                return None

            # 대표 선택: 최신연도(last_year) 공시가격 최대 → 없으면 2016 최대 → 그래도 없으면 첫 행
            p_last = pd.to_numeric(sub[last_year], errors="coerce")
            if p_last.notna().any():
                rep_idx = int(p_last.idxmax())
            else:
                p_2016 = pd.to_numeric(sub["2016"], errors="coerce")
                rep_idx = int(p_2016.idxmax()) if p_2016.notna().any() else int(sub.index[0])

            row = df_num.loc[rep_idx]
            rep_dong = int(row["동"])
            rep_ho = int(row["호"])
            rep_pyeong_raw = row[pyeong_col]

            p2016 = pd.to_numeric(row.get("2016", pd.NA), errors="coerce")
            plast = pd.to_numeric(row.get(last_year, pd.NA), errors="coerce")
            r2016 = r2016_all.loc[rep_idx]
            rlast = rlast_all.loc[rep_idx]

            return {
                "idx": rep_idx,
                "zone": _zone,
                "complex": _complex,
                "pyeong_raw": rep_pyeong_raw,
                "pyeong_fmt": _pyeong_fmt,
                "dong": rep_dong,
                "ho": rep_ho,
                "price_2016": float(p2016) if pd.notna(p2016) else None,
                "price_last": float(plast) if pd.notna(plast) else None,
                "rank_2016": int(r2016) if pd.notna(r2016) else None,
                "rank_last": int(rlast) if pd.notna(rlast) else None,
            }

        def _unit_brief(u: dict) -> str:
            floor = infer_floor_from_ho(u["ho"])
            floor_txt = f"{floor}층" if floor is not None else "층?"
            return f"{u['zone']} / {u['complex']} / {u['pyeong_fmt']} / {u['dong']}동 / {floor_txt}"

        st.caption(
            f"각 단지의 **선택한 평형**에서 **{last_year} 공시가격이 가장 높은 1개 동/호**를 대표로 자동 선택해 비교합니다."
        )

        # =========================
        # 1) 기준단지 선택
        # =========================
        c1, c2, c3 = st.columns(3, gap="small")

        # 기본값: 상단(구역/동/호 선택)에서 이미 선택된 값이 있으면 그걸 우선 사용
        try:
            default_base_zone = zone if zone in zones else zones[0]
        except Exception:
            default_base_zone = zones[0]

        with c1:
            base_zone = st.selectbox(
                "기준단지 구역",
                zones,
                index=(zones.index(default_base_zone) if default_base_zone in zones else 0),
                key="cmp3_base_zone",
            )

        base_complex_list = sorted(df_num[df_num["구역"] == base_zone]["단지명"].dropna().unique().tolist())
        if not base_complex_list:
            st.info("기준단지 구역에 단지 데이터가 없습니다.")
            base_complex = None
        else:
            try:
                default_base_complex = complex_name if (base_zone == zone and complex_name in base_complex_list) else base_complex_list[0]
            except Exception:
                default_base_complex = base_complex_list[0]

            with c2:
                base_complex = st.selectbox(
                    "기준단지 단지명",
                    base_complex_list,
                    index=base_complex_list.index(default_base_complex) if default_base_complex in base_complex_list else 0,
                    key="cmp3_base_complex",
                )

        base_pyeong = None
        if base_complex:
            base_pyeong_list = _get_pyeong_options(base_zone, base_complex)
            if not base_pyeong_list:
                st.info("기준단지에서 평형 후보를 찾지 못했습니다.")
            else:
                # 상단 선택(구역/동/호)의 평형이 있으면 그걸 기본값으로
                default_p = None
                if base_zone == zone and base_complex == complex_name:
                    sel_p = get_pyeong_value(df_num, zone, complex_name, dong, ho)
                    if sel_p is not None and not pd.isna(sel_p):
                        default_p = _fmt_pyeong(sel_p)
                if default_p not in base_pyeong_list:
                    default_p = base_pyeong_list[0]

                with c3:
                    base_pyeong = st.selectbox(
                        "기준단지 평형",
                        base_pyeong_list,
                        index=base_pyeong_list.index(default_p) if default_p in base_pyeong_list else 0,
                        key="cmp3_base_pyeong",
                    )

        base_rep = _pick_representative(base_zone, base_complex, base_pyeong) if (base_complex and base_pyeong) else None
        if base_rep:
            st.markdown(f"- **기준단지(대표):** {_unit_brief(base_rep)}")

        st.divider()

        # =========================
        # 2) 비교단지 1/2 선택
        # =========================
        def _default_other_zone(exclude: str) -> str:
            for z in zones:
                if z != exclude:
                    return z
            return exclude

        d1, d2 = st.columns(2, gap="large")

        with d1:
            st.markdown("**비교단지 1**")
            z1 = st.selectbox("구역", zones, index=zones.index(_default_other_zone(base_zone)) if zones else 0, key="cmp3_z1")
            cplx1_list = sorted(df_num[df_num["구역"] == z1]["단지명"].dropna().unique().tolist())
            cplx1 = st.selectbox("단지명", cplx1_list, key="cmp3_c1") if cplx1_list else None
            p1_list = _get_pyeong_options(z1, cplx1) if cplx1 else []
            p1 = st.selectbox("평형", p1_list, key="cmp3_p1") if p1_list else None
            rep1 = _pick_representative(z1, cplx1, p1) if (cplx1 and p1) else None
            if rep1:
                st.markdown(f"- 대표: {_unit_brief(rep1)}")

        with d2:
            st.markdown("**비교단지 2**")
            z2 = st.selectbox("구역", zones, index=zones.index(_default_other_zone(z1)) if zones else 0, key="cmp3_z2")
            cplx2_list = sorted(df_num[df_num["구역"] == z2]["단지명"].dropna().unique().tolist())
            cplx2 = st.selectbox("단지명", cplx2_list, key="cmp3_c2") if cplx2_list else None
            p2_list = _get_pyeong_options(z2, cplx2) if cplx2 else []
            p2 = st.selectbox("평형", p2_list, key="cmp3_p2") if p2_list else None
            rep2 = _pick_representative(z2, cplx2, p2) if (cplx2 and p2) else None
            if rep2:
                st.markdown(f"- 대표: {_unit_brief(rep2)}")

        st.divider()

        # =========================
        # 3) 비교하기 버튼 → 화살표 그래프 출력
        # =========================
        can_compare = base_rep is not None and rep1 is not None and rep2 is not None
        if st.button("비교하기", key="cmp3_do_compare", type="secondary", disabled=not can_compare):
            def _has_required(u: dict) -> bool:
                return (
                    u is not None
                    and u.get("price_2016") is not None
                    and u.get("price_last") is not None
                    and u.get("rank_2016") is not None
                    and u.get("rank_last") is not None
                )

            if not _has_required(base_rep):
                st.warning("기준단지에 2016/최신연도 데이터가 부족합니다.")
            elif not _has_required(rep1):
                st.warning("비교단지 1에 2016/최신연도 데이터가 부족합니다.")
            elif not _has_required(rep2):
                st.warning("비교단지 2에 2016/최신연도 데이터가 부족합니다.")
            else:
                # --- 요약 표는 기존 렌더 함수 재사용(탭으로 분리) ---
                
                # --- 요약 표: 3개 단지를 한 번에 표시(탭 제거) ---
                def _compact_colname(u: dict) -> str:
                    # 예: "현대1,2차 54평"
                    return f"{u['complex']} {u['pyeong_fmt']}".strip()

                y0 = 2016
                y1 = int(last_year)

                base_nm = _compact_colname(base_rep)
                c1_nm = _compact_colname(rep1)
                c2_nm = _compact_colname(rep2)

                # 상단 요약(짧은 표기)
                st.markdown(
                    f"<div style='text-align:center; font-weight:700; margin:4px 0 10px 0;'>"
                    f"단지: {base_nm} &nbsp;&nbsp;|&nbsp;&nbsp; {c1_nm} &nbsp;&nbsp;|&nbsp;&nbsp; {c2_nm}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                def _f_price(v) -> str:
                    try:
                        return f"{float(v):.2f}"
                    except Exception:
                        return "-"
                def _f_rank(v) -> str:
                    try:
                        return f"{int(v):,}"
                    except Exception:
                        return "-"

                # 2행 헤더(단지명/평형만 상단에 노출)
                rows_tbl = [
                    (
                        y0,
                        _f_price(base_rep["price_2016"]), _f_rank(base_rep["rank_2016"]),
                        _f_price(rep1["price_2016"]), _f_rank(rep1["rank_2016"]),
                        _f_price(rep2["price_2016"]), _f_rank(rep2["rank_2016"]),
                    ),
                    (
                        y1,
                        _f_price(base_rep["price_last"]), _f_rank(base_rep["rank_last"]),
                        _f_price(rep1["price_last"]), _f_rank(rep1["rank_last"]),
                        _f_price(rep2["price_last"]), _f_rank(rep2["rank_last"]),
                    ),
                ]

                html = f"""
                <div class="summary-wrap">
                  <table class="summary-table">
                    <thead>
                      <tr>
                        <th rowspan="2">연도</th>
                        <th colspan="2">{base_nm}</th>
                        <th colspan="2">{c1_nm}</th>
                        <th colspan="2">{c2_nm}</th>
                      </tr>
                      <tr>
                        <th>가격(억)</th><th>순위</th>
                        <th>가격(억)</th><th>순위</th>
                        <th>가격(억)</th><th>순위</th>
                      </tr>
                    </thead>
                    <tbody>
                """
                for (yy, bp, br, c1p, c1r, c2p, c2r) in rows_tbl:
                    html += (
                        f"<tr>"
                        f"<th>{yy}</th>"
                        f"<td>{bp}</td><td>{br}</td>"
                        f"<td>{c1p}</td><td>{c1r}</td>"
                        f"<td>{c2p}</td><td>{c2r}</td>"
                        f"</tr>"
                    )
                html += """</tbody></table></div>"""

                st.markdown(html, unsafe_allow_html=True)
# --- 3개 단지를 하나의 화살표 그래프로 표현 ---
                import matplotlib.pyplot as plt

                # 요청 색상(기준/비교1/비교2)
                COLORS = ["#FF7DB0", "#00CAFF", "#B6F500"]

                fig, ax = plt.subplots()

                # 레전드 라벨은 길이를 줄여(모바일/데스크탑 공통) 단지명+평형만 표시
                base_leg = base_nm
                cmp1_leg = c1_nm
                cmp2_leg = c2_nm# 연도 정렬(전체 연도 표시)
                year_cols_sorted = sorted(year_cols, key=lambda s: int(s))
                start_year = str(year_cols_sorted[0])
                end_year = str(year_cols_sorted[-1])

                # 연도별 전체 순위(공시가격 내림차순)
                ranks_by_year = {y: df_num[y].rank(method="min", ascending=False) for y in year_cols_sorted}

                units = [
                    (base_leg, int(base_rep["idx"]), COLORS[0]),
                    (cmp1_leg, int(rep1["idx"]), COLORS[1]),
                    (cmp2_leg, int(rep2["idx"]), COLORS[2]),
                ]

                # 3개 단지 연도별 순위 시계열 데이터: x=연도, y=압구정 전체 순위
                unit_series = []  # (label, years[int], ranks[float], color)
                all_years = []
                all_ranks = []

                for label, ridx, color in units:
                    yrs = []
                    rs = []
                    for y in year_cols_sorted:
                        rser = ranks_by_year.get(y)
                        if rser is None:
                            continue
                        rval = pd.to_numeric(rser.at[ridx], errors="coerce")
                        if pd.notna(rval):
                            yy = int(y)
                            yrs.append(yy)
                            rs.append(float(rval))
                            all_years.append(yy)
                            all_ranks.append(float(rval))
                    unit_series.append((label, yrs, rs, color))

                graph_mode = st.radio(
                    "하단 비교 그래프",
                    ["레이싱차트(연도별 순위 경쟁)"],
                    index=0,
                    horizontal=True,
                    key="cmp3_rank_graph_mode",
                )

                if not all_years or not all_ranks:
                    st.warning("선택된 단지들에서 연도별 '압구정 전체 순위' 데이터를 찾지 못했습니다.")
                
                else:
                    # 그래프: 레이싱차트(연도별 순위 경쟁)
                    if str(graph_mode).startswith("레이싱"):
                        try:
                            import plotly.graph_objects as go
                        except Exception:
                            st.warning("레이싱차트를 위해 plotly가 필요합니다. requirements.txt에 'plotly'를 추가해 주세요.")
                            st.stop()  # plotly 미설치 시 레이싱차트를 렌더링할 수 없음

                    if str(graph_mode).startswith("레이싱"):
                        # -----------------------
                        # Bar Chart Race (연도별 순위 경쟁)
                        # -----------------------
                        total_n = int(len(df_num))

                        def _short_label(u: dict) -> str:
                            return f"{u.get('complex','')} {u.get('pyeong_fmt','')}".strip()

                        base_lbl = _short_label(base_rep)
                        c1_lbl = _short_label(rep1)
                        c2_lbl = _short_label(rep2)

                        # 라벨이 비어있거나 중복되면 최소한의 구분자를 붙입니다.
                        labels = [base_lbl or "기준", c1_lbl or "비교1", c2_lbl or "비교2"]
                        seen = {}
                        uniq = []
                        for lbl in labels:
                            k = lbl
                            seen[k] = seen.get(k, 0) + 1
                            uniq.append(k if seen[k] == 1 else f"{k}({seen[k]})")
                        base_lbl, c1_lbl, c2_lbl = uniq

                        color_map = {
                            base_lbl: COLORS[0],
                            c1_lbl: COLORS[1],
                            c2_lbl: COLORS[2],
                        }

                        years_int = [int(y) for y in year_cols_sorted]
                        rows = []
                        for y in year_cols_sorted:
                            yi = int(y)
                            for lbl, ridx in [(base_lbl, int(base_rep["idx"])), (c1_lbl, int(rep1["idx"])), (c2_lbl, int(rep2["idx"]))]:
                                rv = pd.to_numeric(ranks_by_year[y].at[ridx], errors="coerce")
                                if pd.notna(rv):
                                    r = float(rv)
                                    score = (total_n - r + 1.0)  # 상위일수록 큰 값
                                    rows.append({"year": yi, "label": lbl, "rank": r, "score": score})

                        df_long = pd.DataFrame(rows)

                        if df_long.empty:
                            st.warning("막대 레이스 그래프를 그릴 데이터가 없습니다.")
                        else:
                            # y축 카테고리 순서를 고정(막대 위치가 연도에 따라 위아래로 바뀌지 않도록)
                            cat_display = [base_lbl, c1_lbl, c2_lbl]  # 화면에서 위→아래로 보이길 원하는 순서
                            cat_order = cat_display[::-1]            # Plotly는 (아래→위)로 카테고리를 쌓으므로 역순 사용

                            def _bar_for_year(yy: int):
                                d = df_long[df_long["year"] == yy].copy()
                                # 카테고리(막대 위치) 고정: 연도별로 순위가 바뀌어도 위/아래 위치가 변하지 않음
                                d = d.set_index("label").reindex(cat_order).reset_index()
                                d["score"] = pd.to_numeric(d["score"], errors="coerce").fillna(0.0)
                                d["rank"] = pd.to_numeric(d["rank"], errors="coerce")

                                bar = go.Bar(
                                    x=d["score"],
                                    y=d["label"],
                                    orientation="h",
                                    marker=dict(color=[color_map.get(lbl, "#999999") for lbl in d["label"]]),
                                    text=[f"{int(r):,}위" if pd.notna(r) else "" for r in d["rank"]],
                                    textposition="outside",
                                    textfont=dict(size=14, family="Arial Black"),
                                    cliponaxis=False,
                                )
                                return bar

                            y0 = years_int[0]
                            frames = [go.Frame(data=[_bar_for_year(yy)], name=str(yy)) for yy in years_int]

                            is_mobile = infer_device_type() == "mobile"

                            race_title = f"{start_year} → {end_year} 연도별 압구정 전체 순위 경쟁 (3개 단지)"
                            if is_mobile:
                                race_title = f"{start_year}→{end_year} 순위 경쟁 (3개 단지)"
                                st.caption("Play 버튼 또는 하단 슬라이더로 연도별 확인")

                            xaxis_title = "상위 점수" if is_mobile else "상위 점수(높을수록 상위)"
                            race_height = 420 if is_mobile else 560
                            race_margin = dict(l=120, r=40, t=120, b=110) if is_mobile else dict(l=190, r=90, t=200, b=145)
                            y_tickfont = dict(size=13, family="Arial Black") if is_mobile else dict(size=15, family="Arial Black")
                            slider_y = -0.18 if is_mobile else -0.22
                            buttons_y = 1.08 if is_mobile else 1.14
                            title_y = 0.96 if is_mobile else 0.98
                            fig_race = go.Figure(
                                data=[_bar_for_year(y0)],
                                layout=go.Layout(
                                    title=dict(text=race_title, x=0.0, xanchor="left", y=title_y, yanchor="top"),
                                    xaxis=dict(title=xaxis_title, range=[0, max(df_long["score"].max(), 1.0) * 1.12], tickfont=dict(size=12), titlefont=dict(size=13)),
                                    yaxis=dict(title="", automargin=True, categoryorder="array", categoryarray=cat_order, tickfont=y_tickfont),
                                    margin=race_margin,
                                    height=race_height,
                                    font=dict(size=12, family="Malgun Gothic"),
                                    updatemenus=[
                                        dict(
                                            type="buttons",
                                            direction="left",
                                            x=0.01, y=buttons_y, xanchor="left", yanchor="bottom",
                                            buttons=[
                                                dict(
                                                    label="Play",
                                                    method="animate",
                                                    args=[None, {"frame": {"duration": 700, "redraw": True},
                                                                 "transition": {"duration": 200},
                                                                 "fromcurrent": True}],
                                                ),
                                                dict(
                                                    label="Pause",
                                                    method="animate",
                                                    args=[[None], {"frame": {"duration": 0, "redraw": False},
                                                                   "mode": "immediate"}],
                                                ),
                                            ],
                                        )
                                    ],
                                    sliders=[
                                        dict(
                                            x=0.01, y=slider_y, len=0.98,
                                            currentvalue=dict(prefix="연도: ", font=dict(size=14, family="Arial Black")),
                                            steps=[
                                                dict(
                                                    method="animate",
                                                    args=[[str(yy)], {"frame": {"duration": 0, "redraw": True},
                                                                      "mode": "immediate"}],
                                                    label=str(yy),
                                                )
                                                for yy in years_int
                                            ],
                                        )
                                    ],
                                ),
                                frames=frames,
                            )

                            st.plotly_chart(fig_race, use_container_width=True)
        else:
            if not can_compare:
                st.caption("기준단지/비교단지 1/2의 구역·단지·평형을 모두 선택하면 [비교하기] 버튼이 활성화됩니다.")
