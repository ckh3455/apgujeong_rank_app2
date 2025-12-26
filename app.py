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
    Streamlit Cloud(리눅스)에서는 윈도우 기본 한글 폰트(맑은 고딕 등)가 없어서
    Matplotlib 그래프에서 한글이 깨질 수 있습니다.

    우선순위:
      1) 레포에 포함된 폰트 파일 (./fonts/*.ttf, *.otf)
      2) 시스템에 설치된 한글 폰트 탐색
    """
    try:
        import os
        from pathlib import Path
        # 1) 레포 포함 폰트(가장 확실)
        here = Path(__file__).resolve().parent
        font_candidates = [
            here / "fonts" / "NanumGothic.ttf",
            here / "fonts" / "NanumGothic.otf",
            here / "fonts" / "NotoSansKR-Regular.otf",
            here / "fonts" / "NotoSansKR-Regular.ttf",
            here / "fonts" / "NotoSansCJKkr-Regular.otf",
        ]
        for fp in font_candidates:
            if fp.exists():
                font_manager.fontManager.addfont(str(fp))
                name = font_manager.FontProperties(fname=str(fp)).get_name()
                plt.rcParams["font.family"] = name
                plt.rcParams["axes.unicode_minus"] = False
                return name

        # 2) 시스템 설치 폰트(있으면 사용)
        candidates = ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR"]
        for name in candidates:
            try:
                plt.rcParams["font.family"] = name
                plt.rcParams["axes.unicode_minus"] = False
                # 실제로 적용 가능한지 간단히 체크(폰트 패밀리로 매칭되는지)
                _ = font_manager.findfont(font_manager.FontProperties(family=name), fallback_to_default=False)
                return name
            except Exception:
                continue

        # 마지막: 폰트 검색(느리지만 한번만)
        for f in font_manager.fontManager.ttflist:
            nm = (getattr(f, "name", "") or "").lower()
            if any(k in nm for k in ["nanum", "malgun", "applegothic", "noto sans cjk", "noto sans kr"]):
                plt.rcParams["font.family"] = f.name
                plt.rcParams["axes.unicode_minus"] = False
                return f.name

        # 실패: 기본 폰트로 진행(한글은 깨질 수 있음)
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

# 순위 라벨(그래프 숫자)
SHOW_RANK_LABELS = True
RANK_LABEL_FONTSIZE = 9
RANK_LABEL_Y_OFFSET = -22  # (음수일수록 위로 더 올라감)
RANK_LABEL_BOLD = True

# =========================
# 한글 폰트 설정 (Matplotlib)
# =========================
def set_korean_matplotlib_font() -> str | None:
    from pathlib import Path

    # 1) 레포에 포함된 폰트 파일 우선 적용(Cloud에서 가장 확실)
    here = Path(__file__).resolve().parent
    font_files = [
        here / "fonts" / "NanumGothic.ttf",
        here / "fonts" / "NotoSansKR-Regular.ttf",
        here / "fonts" / "NotoSansKR-Regular.otf",
    ]
    for fp in font_files:
        if fp.exists():
            font_manager.fontManager.addfont(str(fp))
            name = font_manager.FontProperties(fname=str(fp)).get_name()
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["axes.unicode_minus"] = False
            return name

    # 2) 시스템 폰트(로컬 PC에서는 이 경로로 잘 잡힘)
    candidates = ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans KR", "Noto Sans CJK KR"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["axes.unicode_minus"] = False
            return name

    matplotlib.rcParams["axes.unicode_minus"] = False
    return None



set_korean_matplotlib_font()


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
    </style>
    """,
    unsafe_allow_html=True,
)

YEAR_RE = re.compile(r"^\d{4}$")


def tight_height(n_rows: int) -> int:
    header = 40
    per_row = 36
    padding = 12
    return header + per_row * max(n_rows, 1) + padding


# =========================
# Google Sheets Client (Secrets 기반)
# =========================
@st.cache_resource(show_spinner=False)
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
def load_from_gsheet(spreadsheet_id: str, gid: int = 0) -> pd.DataFrame:
    gc = get_gspread_client()
    sh = gc.open_by_key(spreadsheet_id)
    ws = open_worksheet_by_gid(sh, gid)

    values = ws.get_all_values()
    if not values:
        raise ValueError("시트에 데이터가 없습니다.")

    # 헤더(컬럼) 행 자동 탐지
    # - 기존 스크립트는 '2행=헤더, 3행부터=데이터'를 전제로 했습니다.
    # - 하지만 어떤 시트는 1~2행이 그룹/설명행(예: '30평형대')일 수 있어,
    #   '구역' 컬럼이 포함된 첫 행을 헤더로 간주합니다.
    header_row_index = None
    for i, row in enumerate(values[:50]):  # 상단 50행 내에서 탐색
        norm = [str(x).strip().replace("\n", " ") for x in row]
        if "구역" in norm:
            header_row_index = i
            break

    if header_row_index is None:
        # fallback: 기존 동작(2행 헤더 가정)
        if len(values) < 3:
            raise ValueError("시트에 데이터가 충분하지 않습니다. (헤더 2행 + 데이터 필요)")
        header_row_index = 1

    header = [str(x).strip() for x in values[header_row_index]]
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

        price = pick_row[y]
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
    fig, ax = plt.subplots(figsize=(7.0, 3.8), dpi=130)

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
    fig, ax = plt.subplots(figsize=(7.0, 3.8), dpi=130)

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


# =========================
# 메인
# =========================
st.title("압구정 공동주택 공시가격 랭킹")
st.markdown(APP_DESCRIPTION)
st.markdown(PROMO_TEXT_HTML, unsafe_allow_html=True)

try:
    df_raw = load_from_gsheet(MAIN_SPREADSHEET_ID, MAIN_GID)
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
if not year_cols:
    st.error("연도 컬럼은 있으나 실제 데이터가 있는 연도가 없습니다.")
    st.stop()

zones = sorted(df_num["구역"].dropna().unique().tolist())


def reset_after_zone():
    st.session_state["dong_pair"] = None
    st.session_state["ho"] = None
    st.session_state["confirmed"] = False


def reset_after_dong():
    st.session_state["ho"] = None
    st.session_state["confirmed"] = False


st.session_state.setdefault("zone", None)
st.session_state.setdefault("dong_pair", None)
st.session_state.setdefault("ho", None)
st.session_state.setdefault("confirmed", False)

zone = st.selectbox("구역 선택", zones, index=None, placeholder="구역을 선택하세요",
                    key="zone", on_change=reset_after_zone)

if zone is None:
    dong_pairs = []
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


def fmt_dong(x):
    cn, d = x
    return f"{cn} / {int(d)}동"


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


left, right = st.columns(2, gap="large")

with left:
    st.subheader("구역 내 연도별 랭킹")
    st.caption(f"선택: {zone} / {complex_name} / {dong}동 / {ho}호")
    st.dataframe(
        zone_table,
        use_container_width=True,
        hide_index=True,
        height=tight_height(len(zone_table)),
        column_config={
            "연도": st.column_config.NumberColumn(format="%d", width="small"),
            "공시가격(억)": st.column_config.NumberColumn(format="%.2f", width="small"),
            "구역 내 랭킹": st.column_config.TextColumn(width="small"),
        },
    )

    st.subheader("압구정 전체 연도별 랭킹")
    st.dataframe(
        all_table,
        use_container_width=True,
        hide_index=True,
        height=tight_height(len(all_table)),
        column_config={
            "연도": st.column_config.NumberColumn(format="%d", width="small"),
            "공시가격(억)": st.column_config.NumberColumn(format="%.2f", width="small"),
            "압구정 전체 랭킹": st.column_config.TextColumn(width="small"),
        },
    )

with right:
    st.subheader("순위 변화 그래프")

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

    st.markdown("**구역 내 순위 변화(연도별)**")
    if z_plot.empty:
        st.info("구역 내 순위 그래프를 그릴 데이터가 없습니다.")
    else:
        fig1 = plot_rank_line(
            years=z_plot["연도"].tolist(),
            ranks=z_plot["rank"].tolist(),
            title=f"{zone} / {complex_name} / {dong}동 / {ho}호  (구역 내 순위)",
            style=ZONE_RANK_STYLE,
        )
        st.pyplot(fig1, use_container_width=True)

    st.markdown("**압구정 전체 순위 변화(연도별)**")
    if a_plot.empty:
        st.info("압구정 전체 순위 그래프를 그릴 데이터가 없습니다.")
    else:
        fig2 = plot_rank_line(
            years=a_plot["연도"].tolist(),
            ranks=a_plot["rank"].tolist(),
            title=f"{zone} / {complex_name} / {dong}동 / {ho}호  (압구정 전체 순위)",
            style=ALL_RANK_STYLE,
        )
        st.pyplot(fig2, use_container_width=True)

    st.markdown("**2016년 유사 가격 타구역 비교(가격 추이)**")

    cmp = find_closest_by_2016(
        df_num=df_num,
        base_zone=zone,
        base_key=(zone, complex_name, dong, ho),
        year2016="2016",
    )

    if cmp is None:
        st.info("2016년 가격이 없거나, 비교할 타구역(2016 값 존재) 데이터가 없어 세 번째 그래프를 그릴 수 없습니다.")
    else:
        cmp_zone = cmp["cmp_zone"]
        cmp_complex = cmp["cmp_complex"]
        cmp_dong = cmp["cmp_dong"]
        cmp_ho = cmp["cmp_ho"]

        sel_years, sel_prices = build_price_series(df_num, year_cols, zone, complex_name, dong, ho)
        cmp_years, cmp_prices = build_price_series(df_num, year_cols, cmp_zone, cmp_complex, cmp_dong, cmp_ho)

        sel_map = dict(zip(sel_years, sel_prices))
        cmp_map = dict(zip(cmp_years, cmp_prices))
        common_years = sorted(set(sel_map.keys()) & set(cmp_map.keys()))

        if not common_years:
            st.info("선택/비교 물건의 공통 연도 데이터가 없어 비교 그래프를 그릴 수 없습니다.")
        else:
            sel_prices_aligned = [sel_map[y] for y in common_years]
            cmp_prices_aligned = [cmp_map[y] for y in common_years]

            st.caption(
                f"선택(2016): {cmp['base_price']:.2f}억  |  "
                f"유사타구역(2016): {cmp['cmp_price']:.2f}억  |  "
                f"차이: {cmp['diff']:.2f}억"
            )
            st.caption(f"유사타구역 물건: {unit_str_floor_only(cmp_zone, cmp_complex, cmp_dong, cmp_ho)}")

            fig3 = plot_price_compare(
                years=common_years,
                sel_prices=sel_prices_aligned,
                cmp_prices=cmp_prices_aligned,
                sel_label=f"선택: {zone}",
                cmp_label=f"유사타구역: {cmp_zone}",
            )
            st.pyplot(fig3, use_container_width=True)
