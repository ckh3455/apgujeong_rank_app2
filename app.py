import re
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.pyplot as plt
from matplotlib import font_manager

import gspread
from google.oauth2.service_account import Credentials


# ============================================================
# 0) 환경 / 상수
# ============================================================
KST = ZoneInfo("Asia/Seoul")

DISCLAIMER_TEXT = (
    "※ 본 자료는 **국토교통부 공시가격(2016~현재)** 데이터를 기반으로 계산한 것으로, "
    "재건축 시 **실행될 감정평가액과 차이**가 있을 수 있습니다.\n"
)

# 기본(하드코딩) 시트 설정 (원래 스크립트의 기본값 유지)
DEFAULT_MAIN_SHEET_ID = "1QGSM-mICX9KYa5Izym6sFKVaWwO-o0j86V-KmJ-w0IM"
DEFAULT_LOG_SHEET_ID = "1-V5Ux8yto_8WE6epumN1aWT_D5t_1Dx14VWBZ0SvbbU"
DEFAULT_MAIN_GID = 0
DEFAULT_LOG_GID = 0
DEFAULT_MAX_DATA_ROWS = 10337

# 그래프 스타일 (원본 유지)
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


# ============================================================
# 1) Matplotlib 한글 폰트 (Cloud에서 깨짐 방지: 경로 기반 강제 적용)
# ============================================================
def set_korean_matplotlib_font():
    """
    Streamlit Cloud(리눅스)에서 Matplotlib 한글이 깨지는 문제를 해결하기 위한 폰트 설정.

    우선순위:
      1) 레포에 포함된 ./fonts 폴더의 폰트(.ttf/.otf/.ttc) 자동 탐지
         → FontProperties(fname=...)로 강제 적용(가장 확실)
      2) 시스템 설치 폰트 탐색(로컬에서 잘 동작)
    반환:
      - (font_name, font_prop) 튜플. 찾지 못하면 (None, None)
    """
    try:
        here = Path(__file__).resolve().parent
        fonts_dir = here / "fonts"

        # 1) 레포 포함 폰트 자동 탐지
        if fonts_dir.exists() and fonts_dir.is_dir():
            font_files = []
            for ext in ("*.ttf", "*.otf", "*.ttc"):
                font_files.extend(sorted(fonts_dir.glob(ext)))

            # 가능하면 한글 폰트 우선
            prefer = ["notosanskr", "noto sans kr", "notosanscjk", "nanum", "malgun", "applegothic"]

            def score(p: Path) -> int:
                n = p.name.lower().replace(" ", "")
                for i, kw in enumerate(prefer):
                    if kw.replace(" ", "") in n:
                        return 100 - i
                return 0

            font_files.sort(key=score, reverse=True)

            for fp in font_files:
                try:
                    font_manager.fontManager.addfont(str(fp))
                    prop = font_manager.FontProperties(fname=str(fp))
                    name = prop.get_name()

                    # rcParams는 보조(환경에 따라 title/label이 rcParams를 타는 경우가 있어 함께 설정)
                    matplotlib.rcParams["font.family"] = "sans-serif"
                    matplotlib.rcParams["font.sans-serif"] = [name]
                    matplotlib.rcParams["axes.unicode_minus"] = False
                    return name, prop
                except Exception:
                    continue

        # 2) 시스템 설치 폰트 탐색
        candidates = ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans KR", "Noto Sans CJK KR"]
        for name in candidates:
            try:
                _ = font_manager.findfont(
                    font_manager.FontProperties(family=name),
                    fallback_to_default=False,
                )
                matplotlib.rcParams["font.family"] = name
                matplotlib.rcParams["axes.unicode_minus"] = False
                return name, font_manager.FontProperties(family=name)
            except Exception:
                continue

        matplotlib.rcParams["axes.unicode_minus"] = False
        return None, None
    except Exception:
        return None, None


KR_FONT_NAME, KR_FONT_PROP = set_korean_matplotlib_font()


def _apply_font(ax, prop):
    """축/레이블/틱/범례/주석까지 폰트를 강제 적용(Cloud에서 가장 확실)."""
    if prop is None:
        return

    # title/xlabel/ylabel
    try:
        ax.title.set_fontproperties(prop)
    except Exception:
        pass
    try:
        ax.xaxis.label.set_fontproperties(prop)
        ax.yaxis.label.set_fontproperties(prop)
    except Exception:
        pass

    # tick labels
    try:
        for t in ax.get_xticklabels() + ax.get_yticklabels():
            t.set_fontproperties(prop)
    except Exception:
        pass

    # legend
    try:
        leg = ax.get_legend()
        if leg:
            for t in leg.get_texts():
                t.set_fontproperties(prop)
            if leg.get_title():
                leg.get_title().set_fontproperties(prop)
    except Exception:
        pass

    # annotations / other texts
    try:
        for t in ax.texts:
            t.set_fontproperties(prop)
    except Exception:
        pass


# ============================================================
# 2) UI 기본
# ============================================================
st.set_page_config(page_title="압구정 공시가격 랭킹", layout="centered")

# 폰트 디버그(필요 시)
FONT_DEBUG = st.sidebar.checkbox("폰트 디버그 보기", value=False)
if FONT_DEBUG:
    here = Path(__file__).resolve().parent
    fonts_dir = here / "fonts"
    st.sidebar.write("선택된 폰트:", KR_FONT_NAME)
    st.sidebar.write("fonts/ 존재:", fonts_dir.exists())
    if fonts_dir.exists():
        st.sidebar.write("fonts/ 파일:", [p.name for p in fonts_dir.iterdir() if p.is_file()])

    fig_test, ax_test = plt.subplots(figsize=(6.2, 2.2), dpi=130)
    ax_test.set_title("한글 테스트: 압구정동 / 공시가격 / 123", fontproperties=KR_FONT_PROP)
    ax_test.plot([1, 2, 3], [1, 4, 2])
    _apply_font(ax_test, KR_FONT_PROP)
    st.sidebar.pyplot(fig_test)


# ============================================================
# 3) 인증 / 시트 로딩
# ============================================================
def get_gspread_client() -> gspread.Client:
    """
    우선순위:
      1) Streamlit Cloud: st.secrets["gcp_service_account"] (dict)
      2) 로컬: st.secrets["SERVICE_ACCOUNT_FILE"] (json 파일 경로)
    """
    if "gcp_service_account" in st.secrets:
        info = dict(st.secrets["gcp_service_account"])
        # Streamlit TOML에서 private_key가 "\\n"으로 들어오는 경우가 있어 보정
        if "private_key" in info and isinstance(info["private_key"], str):
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        return gspread.authorize(creds)

    sa_path = str(st.secrets.get("SERVICE_ACCOUNT_FILE", "")).strip()
    if sa_path:
        creds = Credentials.from_service_account_file(
            sa_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        return gspread.authorize(creds)

    raise ValueError(
        "앱 실행에 필요한 Streamlit Secrets 설정이 없습니다: gcp_service_account 또는 SERVICE_ACCOUNT_FILE\n"
        "Streamlit Cloud에서는 Settings → Secrets에 gcp_service_account를 TOML로 등록하세요."
    )


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]
    return df


def load_from_gsheet(spreadsheet_id: str, gid: int) -> pd.DataFrame:
    gc = get_gspread_client()
    sh = gc.open_by_key(spreadsheet_id)

    # gid로 worksheet 찾기
    ws = None
    try:
        for w in sh.worksheets():
            if int(w.id) == int(gid):
                ws = w
                break
    except Exception:
        ws = None

    if ws is None:
        ws = sh.sheet1  # fallback

    values = ws.get_all_values()
    if not values:
        raise ValueError("시트에 데이터가 없습니다.")

    # 헤더(컬럼) 행 자동 탐지
    # - 원본 전제: 2행=헤더, 3행부터=데이터
    # - 실제 시트에서 1~2행이 설명/그룹행(예: '30평형대')인 경우가 있어,
    #   '구역' 컬럼이 포함된 첫 행을 헤더로 사용합니다.
    header_row_index = None
    for i, row in enumerate(values[:50]):  # 상단 50행 내에서 탐색
        norm = [str(x).strip().replace("\n", " ") for x in row]
        if "구역" in norm:
            header_row_index = i
            break

    if header_row_index is None:
        # fallback: 기존 방식(2행 헤더)
        if len(values) < 3:
            raise ValueError("시트에 데이터가 충분하지 않습니다. (헤더 2행 + 데이터 필요)")
        header_row_index = 1

    header = [str(x).strip() for x in values[header_row_index]]
    data = values[header_row_index + 1 :]
    df = pd.DataFrame(data, columns=header)
    return _normalize_columns(df)


def append_log_row(log_spreadsheet_id: str, log_gid: int, row: list[str]) -> None:
    if not log_spreadsheet_id:
        return
    gc = get_gspread_client()
    sh = gc.open_by_key(log_spreadsheet_id)

    ws = None
    try:
        for w in sh.worksheets():
            if int(w.id) == int(log_gid):
                ws = w
                break
    except Exception:
        ws = None

    if ws is None:
        ws = sh.sheet1

    ws.append_row(row, value_input_option="USER_ENTERED")


# ============================================================
# 4) 데이터 정리 / 검증
# ============================================================
def clean_and_validate(df: pd.DataFrame) -> pd.DataFrame:
    required = ["구역", "단지명", "동", "호"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"데이터 정리 실패: 필수 컬럼이 없습니다: {', '.join(missing)} (현재 컬럼: {list(df.columns)})")

    # 문자열 정리
    for c in ["구역", "단지명", "동", "호"]:
        df[c] = df[c].astype(str).str.strip()

    # 연도 컬럼 찾기 (원본 로직 유지: 2016~현재 숫자 컬럼 탐색)
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

    # 숫자 변환(억 단위 등 원본 구조 유지: float로)
    for y in year_cols:
        col = str(y)
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", "").str.strip(), errors="coerce")

    df["__year_cols__"] = [year_cols] * len(df)  # 편의 저장
    return df


# ============================================================
# 5) 그래프
# ============================================================
def plot_rank_line(years: list[int], ranks: list[int], title: str, style: dict):
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

    ax.set_title(title, fontproperties=KR_FONT_PROP)
    ax.set_xlabel("연도", fontproperties=KR_FONT_PROP)
    ax.set_ylabel("순위 (작을수록 상위)", fontproperties=KR_FONT_PROP)

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
                fontproperties=KR_FONT_PROP,
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="none", alpha=0.9),
            )

    ax.grid(True, alpha=0.3)
    _apply_font(ax, KR_FONT_PROP)
    fig.tight_layout()
    return fig


def plot_price_compare(
    years: list[int],
    sel_prices: list[float],
    cmp_prices: list[float],
    sel_label: str,
    cmp_label: str,
):
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

    ax.set_title("2016 유사 가격 타구역 비교: 공시가격 추이", fontproperties=KR_FONT_PROP)
    ax.set_xlabel("연도", fontproperties=KR_FONT_PROP)
    ax.set_ylabel("공시가격(억)", fontproperties=KR_FONT_PROP)

    ax.set_xticks(years)
    ax.set_xticklabels([str(y) for y in years], rotation=0)

    # 마지막 연도만 라벨
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
        fontproperties=KR_FONT_PROP,
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
        fontproperties=KR_FONT_PROP,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="none", alpha=0.9),
    )

    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    _apply_font(ax, KR_FONT_PROP)
    fig.tight_layout()
    return fig


# ============================================================
# 6) 본문
# ============================================================
st.title("압구정 공시가격 랭킹")
st.write(DISCLAIMER_TEXT)

# 시트 설정(Secrets 우선, 없으면 기본값)
MAIN_SPREADSHEET_ID = str(st.secrets.get("main_sheet_id", DEFAULT_MAIN_SHEET_ID)).strip()
MAIN_GID = int(st.secrets.get("main_gid", DEFAULT_MAIN_GID))
MAX_DATA_ROWS = int(st.secrets.get("max_data_rows", DEFAULT_MAX_DATA_ROWS))

LOG_SPREADSHEET_ID = str(st.secrets.get("log_sheet_id", DEFAULT_LOG_SHEET_ID)).strip()
LOG_GID = int(st.secrets.get("log_gid", DEFAULT_LOG_GID))

# 데이터 로딩
with st.spinner("시트에서 데이터를 불러오는 중..."):
    df_raw = load_from_gsheet(MAIN_SPREADSHEET_ID, MAIN_GID)
    df = clean_and_validate(df_raw)

year_cols = df["__year_cols__"].iloc[0]
df = df.drop(columns=["__year_cols__"], errors="ignore")

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

sel = df_d[df_d["호"] == ho].copy()
if sel.empty:
    st.error("선택한 항목의 데이터가 없습니다.")
    st.stop()

# 선택 행(첫 행)
row = sel.iloc[0]

# 순위 계산(연도별): 같은 연도에서 값이 큰 순으로 1등
rank_rows = []
for y in year_cols:
    col = str(y)
    # 결측 제외
    s = df_zone[["구역", "단지명", "동", "호", col]].copy()
    s = s.dropna(subset=[col])
    if s.empty or pd.isna(row[col]):
        continue
    # 내림차순 rank (값이 클수록 상위)
    s["rank"] = s[col].rank(method="min", ascending=False)
    # 선택 row의 rank
    key = (zone, complex_name, dong, ho)
    sel_rank = s[(s["구역"] == key[0]) & (s["단지명"] == key[1]) & (s["동"] == key[2]) & (s["호"] == key[3])]
    if sel_rank.empty:
        continue
    rank_rows.append({"연도": y, "rank": int(sel_rank["rank"].iloc[0])})

z_plot = pd.DataFrame(rank_rows).sort_values("연도")

# 압구정 전체 rank(전체 df 기준)
apgu_rows = []
for y in year_cols:
    col = str(y)
    s = df[["구역", "단지명", "동", "호", col]].copy()
    s = s.dropna(subset=[col])
    if s.empty or pd.isna(row[col]):
        continue
    s["rank"] = s[col].rank(method="min", ascending=False)
    key = (zone, complex_name, dong, ho)
    sel_rank = s[(s["구역"] == key[0]) & (s["단지명"] == key[1]) & (s["동"] == key[2]) & (s["호"] == key[3])]
    if sel_rank.empty:
        continue
    apgu_rows.append({"연도": y, "rank": int(sel_rank["rank"].iloc[0])})

a_plot = pd.DataFrame(apgu_rows).sort_values("연도")

# 그래프 출력
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
        style=APGU_RANK_STYLE,
    )
    st.pyplot(fig2, use_container_width=True)

# 로그 기록(선택)
try:
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    append_log_row(
        LOG_SPREADSHEET_ID,
        LOG_GID,
        [now, zone, complex_name, str(dong), str(ho)],
    )
except Exception:
    pass

# 유사타구역 비교(원본 로직 단순화: 2016 기준 가장 가까운 타구역 1개)
st.markdown("**2016 유사 가격 타구역 비교: 공시가격 추이**")
base_year = 2016
if str(base_year) not in df.columns or pd.isna(row.get(str(base_year), None)):
    st.info("2016년 가격이 없어서 비교 그래프를 그릴 수 없습니다.")
else:
    base_val = float(row[str(base_year)])
    # 다른 구역 중 2016 값이 있는 후보
    candidates = df[(df["구역"] != zone) & df[str(base_year)].notna()].copy()
    if candidates.empty:
        st.info("비교할 타구역 데이터가 없습니다.")
    else:
        candidates["diff"] = (candidates[str(base_year)].astype(float) - base_val).abs()
        cmp_row = candidates.sort_values("diff").iloc[0]
        cmp_zone = cmp_row["구역"]

        # 선택/비교 가격 시계열
        years = []
        sel_prices = []
        cmp_prices = []
        for y in year_cols:
            col = str(y)
            sv = row.get(col, None)
            cv = cmp_row.get(col, None)
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
