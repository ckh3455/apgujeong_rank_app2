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
APP_DESCRIPTION = """
이 앱은 **구역/단지/평형**을 선택하여 최대 3개까지 **연도별 공시가격(억)** 추이를 한 그래프에서 비교합니다.

- 상단에서 **비교선택 1~3**을 지정한 뒤 **[비교]** 버튼을 누르면 그래프가 출력됩니다.
- 비교는 평형 단위로 집계(동일 구역/단지/평형의 연도별 공시가격을 평균)하여 표시합니다.
- 데이터는 공시가격 기반이며, 실거래/감정평가와 차이가 있을 수 있습니다.
"""

PROMO_TEXT_HTML = """
<style>
  .promo-box{
    border: 1px solid rgba(49,51,63,.15);
    border-radius: 14px;
    padding: 14px 16px;
    background: rgba(250,250,252,.75);
    margin: 10px 0 18px 0;
  }
  .promo-title{ font-size: 1.05rem; margin-bottom: 6px; }
  .promo-line{ font-size: 0.98rem; line-height: 1.35rem; }
  .promo-small{ margin-top: 6px; font-size: 0.9rem; color: rgba(49,51,63,.75); }
</style>
<div class="promo-box">
  <div class="promo-title">📞 <b>압구정 원 부동산</b></div>
  <div class="promo-line">압구정 재건축 전문 컨설팅 · <b>가액보다 순위가 중요한 압구정</b></div>
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

# 막대그래프 스타일(3번 비교 그래프)
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
        border-bottom: 1px solid rgba(49,51,63,.20);
        background: rgba(250,250,252,.90);
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



def normalize_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible wrapper: normalize/clean the raw sheet dataframe."""
    return _clean_main_df(df_raw)

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
    ax.legend(loc="best")
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
st.title("압구정 공동주택 공시가격 랭킹")
st.markdown(APP_DESCRIPTION)
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

# =========================
# 메인 (간단 비교 UI)
# =========================
_validate_runtime_config()

st.title("압구정 공시가격 비교")
st.markdown(APP_DESCRIPTION)

with st.spinner("데이터를 불러오는 중..."):
    df_raw = load_from_gsheet(
        spreadsheet_id=MAIN_SPREADSHEET_ID,
        gid=MAIN_GID,
        worksheet_name=MAIN_WORKSHEET_NAME if MAIN_WORKSHEET_NAME else None,
    )

df = normalize_df(df_raw)
year_cols = _detect_year_cols(df)
if not year_cols:
    st.error("연도 컬럼(예: 2016~2025)을 찾지 못했습니다. 시트의 헤더를 확인해 주세요.")
    st.stop()

df_num = cast_numeric(df, year_cols)

pcol = detect_pyeong_col(df_num)

# -------------------------
# 비교 유닛(구역/단지/평형) 목록 구성
# -------------------------
group_fields = ["구역", "단지명"]
if pcol:
    group_fields.append(pcol)

groups = df_num[group_fields].drop_duplicates().copy()
groups = groups.dropna(subset=["구역", "단지명"]).copy()

def _group_label(row: pd.Series) -> str:
    z = str(row["구역"]).strip()
    c = str(row["단지명"]).strip()
    if pcol:
        p = _fmt_pyeong(row[pcol])
        return f"{z} / {c} / {p}"
    return f"{z} / {c}"

groups["label"] = groups.apply(_group_label, axis=1)
groups = groups.sort_values("label").reset_index(drop=True)

labels = groups["label"].tolist()
label_to_key: dict[str, tuple] = {}
for _, r in groups.iterrows():
    if pcol:
        label_to_key[r["label"]] = (str(r["구역"]).strip(), str(r["단지명"]).strip(), r[pcol])
    else:
        label_to_key[r["label"]] = (str(r["구역"]).strip(), str(r["단지명"]).strip(), None)

# -------------------------
# 평형 단위 가격 시계열(평균 집계)
# -------------------------
def build_group_price_series(
    df_in: pd.DataFrame,
    year_cols_in: list[str],
    zone: str,
    complex_name: str,
    pyeong_val,
) -> tuple[list[int], list[float]]:
    m = (df_in["구역"] == zone) & (df_in["단지명"] == complex_name)
    if pcol:
        # 평형 값은 형태가 다양하므로 문자열 비교로 완화
        # - 원본 값 그대로 저장해 둔 key(pyeong_val)와 동일한 row를 우선 매칭
        m = m & (df_in[pcol] == pyeong_val)

    sub = df_in.loc[m, year_cols_in].copy()
    if sub.empty:
        return [], []

    years: list[int] = []
    vals: list[float] = []
    for y in year_cols_in:
        s = pd.to_numeric(sub[y], errors="coerce")
        v = float(s.mean()) if s.notna().any() else None
        if v is None or pd.isna(v):
            continue
        years.append(int(y))
        vals.append(float(v))
    return years, vals

# -------------------------
# 다중 비교 그래프 (최대 3개)
# -------------------------
COMPARE_LINE_STYLES = [
    dict(line_color="#1b6e3a", line_width=3.2, line_style="-", marker="o", marker_size=8, marker_face="#ffffff", marker_edge="#1b6e3a"),
    dict(line_color="#5b2b7a", line_width=3.2, line_style="-", marker="s", marker_size=8, marker_face="#ffffff", marker_edge="#5b2b7a"),
    dict(line_color="#1f77b4", line_width=3.2, line_style="-", marker="^", marker_size=8, marker_face="#ffffff", marker_edge="#1f77b4"),
]

def plot_multi_price_lines(series: list[tuple[str, list[int], list[float]]]):
    fig, ax = plt.subplots(figsize=(7.6, 4.8), dpi=RANK_FIG_DPI)

    for i, (lab, yrs, vals) in enumerate(series):
        stl = COMPARE_LINE_STYLES[i % len(COMPARE_LINE_STYLES)]
        ax.plot(
            yrs,
            vals,
            label=lab,
            color=stl["line_color"],
            linewidth=stl["line_width"],
            linestyle=stl["line_style"],
            marker=stl["marker"],
            markersize=stl["marker_size"],
            markerfacecolor=stl["marker_face"],
            markeredgecolor=stl["marker_edge"],
            markeredgewidth=1.4,
        )
        # 마지막 값 라벨
        if yrs:
            ax.annotate(
                f"{vals[-1]:.2f}억",
                (yrs[-1], vals[-1]),
                textcoords="offset points",
                xytext=(6, 6),
                ha="left",
                fontsize=10,
                fontweight="bold",
            )

    ax.set_title("연도별 공시가격 비교(평형 단위 평균)")
    ax.set_xlabel("연도")
    ax.set_ylabel("공시가격(억)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", frameon=True, framealpha=0.9)
    fig.tight_layout()
    return fig

# -------------------------
# UI: 비교선택 1~3 + 비교 버튼
# -------------------------
st.markdown("### 비교 선택")

col1, col2, col3 = st.columns(3)
sel1 = col1.selectbox("비교선택 1", labels, index=None, placeholder="필수 선택")
sel2 = col2.selectbox("비교선택 2", ["선택 안함"] + labels, index=0)
sel3 = col3.selectbox("비교선택 3", ["선택 안함"] + labels, index=0)

do_compare = st.button("비교", type="primary")

if do_compare:
    picked = []
    for s in [sel1, sel2, sel3]:
        if not s or s == "선택 안함":
            continue
        if s not in picked:
            picked.append(s)

    if not picked:
        st.warning("비교선택 1을 포함해 최소 1개를 선택해 주세요.")
        st.stop()

    # 시계열 생성
    series = []
    for lab in picked[:3]:
        z, c, pv = label_to_key[lab]
        yrs, vals = build_group_price_series(df_num, year_cols, z, c, pv)
        if not yrs:
            st.warning(f"데이터가 없어 제외: {lab}")
            continue
        series.append((lab, yrs, vals))

    if not series:
        st.error("선택한 항목들에서 표시할 수 있는 연도별 데이터가 없습니다.")
        st.stop()

    # 요약표: 2016/최신연도(가능하면 2025) 값
    last_year = max(int(y) for y in year_cols)
    base_year = 2016 if "2016" in year_cols else min(int(y) for y in year_cols)

    rows = []
    for lab, yrs, vals in series:
        m = dict(zip(yrs, vals))
        p0 = m.get(base_year, None)
        p1 = m.get(last_year, None)
        rows.append(
            {
                "대상": lab,
                f"{base_year} 가격(억)": (f"{p0:.2f}" if p0 is not None else "-"),
                f"{last_year} 가격(억)": (f"{p1:.2f}" if p1 is not None else "-"),
                "증감(억)": (f"{(p1 - p0):.2f}" if (p0 is not None and p1 is not None) else "-"),
            }
        )

    st.markdown("#### 요약")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("#### 비교 그래프")
    fig = plot_multi_price_lines(series)
    st.pyplot(fig, use_container_width=True)
else:
    st.info("상단에서 비교 대상을 선택한 뒤 [비교] 버튼을 누르면 그래프가 표시됩니다.")
