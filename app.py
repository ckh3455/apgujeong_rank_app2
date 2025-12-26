import re
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

import gspread
from google.oauth2.service_account import Credentials

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import font_manager

# =========================
# 기본 설정
# =========================
KST = ZoneInfo("Asia/Seoul")

DISCLAIMER_TEXT = (
    "※ 본 자료는 **국토교통부 공시가격(2016~현재)** 데이터를 기반으로 계산한 것으로, "
    "재건축 시 **실행될 감정평가액과 차이**가 있을 수 있습니다.\n"
)

# =========================
# 한글 폰트 설정 (Matplotlib)
# =========================
def set_korean_matplotlib_font() -> str | None:
    """
    Streamlit Cloud(리눅스)에서 Matplotlib 한글 깨짐 해결:
    - 레포의 ./fonts 폴더에 넣어둔 폰트 파일(.ttf/.otf/.ttc)을 addfont()로 등록
    - 그 다음 기존 후보 폰트명(NanumGothic 등)을 rcParams로 지정
    """
    from pathlib import Path

    # 1) 레포에 포함된 폰트 파일을 Matplotlib 폰트매니저에 등록
    here = Path(__file__).resolve().parent
    fonts_dir = here / "fonts"
    if fonts_dir.exists():
        for ext in ("*.ttf", "*.otf", "*.ttc"):
            for fp in fonts_dir.glob(ext):
                try:
                    font_manager.fontManager.addfont(str(fp))
                except Exception:
                    pass

        # (환경에 따라 캐시 때문에 새 폰트를 못 보는 경우가 있어 시도)
        try:
            font_manager._load_fontmanager(try_read_cache=False)
        except Exception:
            pass

    # 2) 기존 방식대로 폰트 이름을 찾아 적용
    candidates = ["NanumGothic", "Nanum Gothic", "Malgun Gothic", "AppleGothic", "Noto Sans KR", "Noto Sans CJK KR"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["axes.unicode_minus"] = False
            return name

    matplotlib.rcParams["axes.unicode_minus"] = False
    return None


# 앱 시작 시 폰트 설정
set_korean_matplotlib_font()

# =========================
# 스타일/파라미터
# =========================
ZONE_RANK_STYLE = dict(
    line_color="tab:blue",
    line_width=2.4,
    line_style="-",
    marker="o",
    marker_size=5.5,
    marker_face="white",
    marker_edge="tab:blue",
    marker_edge_width=1.5,
)
APGU_RANK_STYLE = dict(
    line_color="tab:orange",
    line_width=2.4,
    line_style="-",
    marker="o",
    marker_size=5.5,
    marker_face="white",
    marker_edge="tab:orange",
    marker_edge_width=1.5,
)

SEL_PRICE_STYLE = dict(
    line_color="tab:green",
    line_width=2.4,
    line_style="-",
    marker="o",
    marker_size=5.5,
    marker_face="white",
    marker_edge="tab:green",
    marker_edge_width=1.5,
)
CMP_PRICE_STYLE = dict(
    line_color="tab:purple",
    line_width=2.4,
    line_style="--",
    marker="s",
    marker_size=5.5,
    marker_face="white",
    marker_edge="tab:purple",
    marker_edge_width=1.5,
)

SHOW_RANK_LABELS = True
RANK_LABEL_FONTSIZE = 10
RANK_LABEL_Y_OFFSET = 10

# =========================
# Google Sheet 설정
# =========================
MAIN_SPREADSHEET_ID = st.secrets.get("main_sheet_id", "1QGSM-mICX9KYa5Izym6sFKVaWwO-o0j86V-KmJ-w0IM")
MAIN_GID = int(st.secrets.get("main_gid", 0))
MAX_DATA_ROWS = int(st.secrets.get("max_data_rows", 10337))

LOG_SPREADSHEET_ID = st.secrets.get("log_sheet_id", "1-V5Ux8yto_8WE6epumN1aWT_D5t_1Dx14VWBZ0SvbbU")
LOG_GID = int(st.secrets.get("log_gid", 0))


def get_gspread_client() -> gspread.Client:
    """
    우선순위:
      1) Streamlit Cloud: st.secrets["gcp_service_account"] (dict)
      2) 로컬: st.secrets["SERVICE_ACCOUNT_FILE"] (json 파일 경로)
    """
    if "gcp_service_account" in st.secrets:
        info = dict(st.secrets["gcp_service_account"])
        if "private_key" in info and isinstance(info["private_key"], str):
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        return gspread.authorize(creds)

    service_account_file = st.secrets.get("SERVICE_ACCOUNT_FILE", "")
    if not service_account_file:
        raise ValueError("SERVICE_ACCOUNT_FILE이 설정되어 있지 않습니다.")
    creds = Credentials.from_service_account_file(
        service_account_file,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return gspread.authorize(creds)


def find_worksheet_by_gid(sh: gspread.Spreadsheet, gid: int):
    for ws in sh.worksheets():
        if int(ws.id) == int(gid):
            return ws
    return None


def load_from_gsheet(spreadsheet_id: str, gid: int) -> pd.DataFrame:
    gc = get_gspread_client()
    sh = gc.open_by_key(spreadsheet_id)
    ws = find_worksheet_by_gid(sh, gid)
    if ws is None:
        ws = sh.sheet1

    values = ws.get_all_values()
    if len(values) < 3:
        raise ValueError("시트에 데이터가 충분하지 않습니다. (헤더 2행 + 데이터 필요)")

    header = [str(x).strip() for x in values[1]]  # 2행
    data = values[2:]  # 3행부터
    df = pd.DataFrame(data, columns=header)
    return _normalize_columns(df)


def append_log_row(log_spreadsheet_id: str, log_gid: int, row: list[str]) -> None:
    gc = get_gspread_client()
    sh = gc.open_by_key(log_spreadsheet_id)
    ws = find_worksheet_by_gid(sh, log_gid)
    if ws is None:
        ws = sh.sheet1
    ws.append_row(row, value_input_option="USER_ENTERED")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]
    return df


def parse_float(x):
    if x is None:
        return np.nan
    s = str(x).strip()
    if s == "" or s.lower() == "nan":
        return np.nan
    s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return np.nan


def clean_and_validate(df: pd.DataFrame) -> pd.DataFrame:
    required = ["구역", "단지명", "동", "호"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"데이터 정리 실패: 필수 컬럼이 없습니다: {', '.join(missing)} (현재 컬럼: {list(df.columns)})")

    # 문자열 정리
    for c in required:
        df[c] = df[c].astype(str).str.strip()

    # 연도 컬럼 자동 탐색 (2016~현재)
    year_cols = []
    for c in df.columns:
        cc = str(c).strip()
        if re.fullmatch(r"\d{4}", cc):
            y = int(cc)
            if 2010 <= y <= 2100:
                year_cols.append(y)
    year_cols = sorted(set(year_cols))
    if not year_cols:
        raise ValueError("데이터 정리 실패: 연도 컬럼(예: 2016, 2017...)을 찾지 못했습니다.")

    # 숫자 변환
    for y in year_cols:
        col = str(y)
        df[col] = df[col].apply(parse_float)

    df["__year_cols__"] = [year_cols] * len(df)
    return df


def compute_rank_tables(df: pd.DataFrame, year_cols: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    - zone_rank: 구역별 연도별 rank (값이 클수록 상위, rank 1이 최고)
    - apgu_rank: 전체(압구정 전체) 연도별 rank
    """
    # 구역 내 랭킹용: (구역, 단지명, 동, 호) 키 유지
    zone_rank = df[["구역", "단지명", "동", "호"] + [str(y) for y in year_cols]].copy()

    # 압구정 전체 랭킹용(전체 df 기준)
    apgu_rank = df[["구역", "단지명", "동", "호"] + [str(y) for y in year_cols]].copy()

    # 연도별 rank 계산
    for y in year_cols:
        col = str(y)
        # 구역 내 랭킹
        zone_rank[col + "_rank"] = zone_rank.groupby("구역")[col].rank(method="min", ascending=False)
        # 전체 랭킹
        apgu_rank[col + "_rank"] = apgu_rank[col].rank(method="min", ascending=False)

    return zone_rank, apgu_rank


def plot_rank_line(years, ranks, title, style):
    fig, ax = plt.subplots(figsize=(7.0, 3.8), dpi=130)

    ax.plot(
        years,
        ranks,
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
                f"{int(y)}",
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


def plot_price_compare(years, sel_prices, cmp_prices, sel_label, cmp_label):
    fig, ax = plt.subplots(figsize=(7.0, 3.8), dpi=130)

    ax.plot(
        years,
        sel_prices,
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
        years,
        cmp_prices,
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

    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    return fig


# =========================
# Streamlit UI
# =========================
st.set_page_config(page_title="압구정 공시가격 랭킹", layout="centered")
st.title("압구정 공시가격 랭킹")
st.write(DISCLAIMER_TEXT)

with st.spinner("시트에서 데이터를 불러오는 중..."):
    df_raw = load_from_gsheet(MAIN_SPREADSHEET_ID, MAIN_GID)
    df = clean_and_validate(df_raw)

year_cols = df["__year_cols__"].iloc[0]
df = df.drop(columns=["__year_cols__"], errors="ignore")

# 랭킹 테이블 준비
zone_rank, apgu_rank = compute_rank_tables(df, year_cols)

# 선택 UI
zones = sorted(df["구역"].dropna().unique().tolist())
zone = st.selectbox("구역 선택", zones)

df_zone = df[df["구역"] == zone].copy()
complexes = sorted(df_zone["단지명"].dropna().unique().tolist())
complex_name = st.selectbox("단지 선택", complexes)

df_c = df_zone[df_zone["단지명"] == complex_name].copy()
dongs = sorted(df_c["동"].dropna().unique().tolist())
dong = st.selectbox("동 선택", dongs)

df_d = df_c[df_c["동"] == dong].copy()
hos = sorted(df_d["호"].dropna().unique().tolist())
ho = st.selectbox("호 선택", hos)

key_mask = (
    (df["구역"] == zone)
    & (df["단지명"] == complex_name)
    & (df["동"] == dong)
    & (df["호"] == ho)
)
sel = df[key_mask].copy()
if sel.empty:
    st.error("선택한 항목의 데이터가 없습니다.")
    st.stop()

row = sel.iloc[0]

# =========================
# 1) 구역 내 순위 변화
# =========================
rank_rows = []
for y in year_cols:
    col_rank = str(y) + "_rank"
    m = (
        (zone_rank["구역"] == zone)
        & (zone_rank["단지명"] == complex_name)
        & (zone_rank["동"] == dong)
        & (zone_rank["호"] == ho)
    )
    r = zone_rank.loc[m, col_rank]
    if r.empty or pd.isna(r.iloc[0]):
        continue
    rank_rows.append({"연도": y, "rank": float(r.iloc[0])})

z_plot = pd.DataFrame(rank_rows)
if not z_plot.empty:
    z_plot = z_plot.sort_values("연도")

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

# =========================
# 2) 압구정 전체 순위 변화
# =========================
apgu_rows = []
for y in year_cols:
    col_rank = str(y) + "_rank"
    m = (
        (apgu_rank["구역"] == zone)
        & (apgu_rank["단지명"] == complex_name)
        & (apgu_rank["동"] == dong)
        & (apgu_rank["호"] == ho)
    )
    r = apgu_rank.loc[m, col_rank]
    if r.empty or pd.isna(r.iloc[0]):
        continue
    apgu_rows.append({"연도": y, "rank": float(r.iloc[0])})

a_plot = pd.DataFrame(apgu_rows)
if not a_plot.empty:
    a_plot = a_plot.sort_values("연도")

st.markdown("**압구정 전체 순위 변화(연도별)**")
if a_plot.empty:
    st.info("압구정 전체 순위 그래프를 그릴 데이터가 없습니다.")
else:
    fig2 = plot_rank_line(
        years=a_plot["연도"].tolist(),
        ranks=a_plot["rank"].tolist(),
        title=f"{zone} / {complex_name} / {dong}동 / {ho}호  (압구정 전체 순위)",
        style=APGU_RANK_STYLE,
    )
    st.pyplot(fig2, use_container_width=True)

# =========================
# 3) 로그 기록
# =========================
try:
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    append_log_row(LOG_SPREADSHEET_ID, LOG_GID, [now, zone, complex_name, str(dong), str(ho)])
except Exception:
    pass

# =========================
# 4) 2016 유사 가격 타구역 비교
# =========================
st.markdown("**2016 유사 가격 타구역 비교: 공시가격 추이**")
base_year = 2016
if str(base_year) not in df.columns or pd.isna(row.get(str(base_year), np.nan)):
    st.info("2016년 가격이 없어서 비교 그래프를 그릴 수 없습니다.")
else:
    base_val = float(row[str(base_year)])
    candidates = df[(df["구역"] != zone) & df[str(base_year)].notna()].copy()
    if candidates.empty:
        st.info("비교할 타구역 데이터가 없습니다.")
    else:
        candidates["diff"] = (candidates[str(base_year)].astype(float) - base_val).abs()
        cmp_row = candidates.sort_values("diff").iloc[0]
        cmp_zone = cmp_row["구역"]

        years = []
        sel_prices = []
        cmp_prices = []
        for y in year_cols:
            col = str(y)
            sv = row.get(col, np.nan)
            cv = cmp_row.get(col, np.nan)
            if pd.isna(sv) or pd.isna(cv):
                continue
            years.append(int(y))
            sel_prices.append(float(sv))
            cmp_prices.append(float(cv))

        if not years:
            st.info("비교 가능한 연도 데이터가 없습니다.")
        else:
            fig3 = plot_price_compare(
                years=years,
                sel_prices=sel_prices,
                cmp_prices=cmp_prices,
                sel_label=f"선택: {zone}",
                cmp_label=f"유사타구역: {cmp_zone}",
            )
            st.pyplot(fig3, use_container_width=True)
