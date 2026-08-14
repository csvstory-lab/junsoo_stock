"""
전체 상장 종목 GP/A 자동 스캔 스크립트
GitHub Actions가 매일 이 스크립트를 실행해서 data/gpa_ranking.json 을 만듭니다.
Streamlit 앱(app.py)은 이 파일을 그냥 읽기만 하므로, 사이트 접속 시 대기시간이 없습니다.
"""
import os
import json
import time
from datetime import datetime

import pandas as pd
import FinanceDataReader as fdr

try:
    from opendartreader import OpenDartReader
except ImportError:
    import OpenDartReader

API_KEY = os.environ["DART_API_KEY"]
MAX_STOCKS = int(os.environ.get("MAX_STOCKS", "0"))  # 0이면 전체 스캔, 테스트할 땐 30 등으로 제한
YEAR = int(os.environ.get("SCAN_YEAR", str(datetime.today().year - 1)))


def get_universe() -> pd.DataFrame:
    """코스피+코스닥 전체 종목 목록을 가져오고, 관리종목은 제외합니다."""
    df = fdr.StockListing("KRX")
    df = df.dropna(subset=["Code"])

    try:
        admin = fdr.StockListing("KRX-ADMINISTRATIVE")
        admin_codes = set(admin["Code"].astype(str))
        before = len(df)
        df = df[~df["Code"].astype(str).isin(admin_codes)]
        print(f"관리종목 {before - len(df)}개 제외")
    except Exception as e:
        print(f"관리종목 목록 제외 실패(무시하고 진행): {e}")

    return df


def resolve_corp_code(corp_codes: pd.DataFrame, stock_code: str):
    matched = corp_codes[corp_codes["stock_code"] == stock_code]
    if matched.empty:
        return None, None
    row = matched.iloc[0]
    return row["corp_code"], row["corp_name"]


def get_amount(df: pd.DataFrame, account_name: str):
    matched = df[df["account_nm"] == account_name]["thstrm_amount"].values
    if len(matched) == 0:
        return None
    try:
        return float(str(matched[0]).replace(",", ""))
    except ValueError:
        return None


def compute_gpa(dart, corp_code: str, year: int):
    for fs_div in ("CFS", "OFS"):  # 연결재무제표 먼저, 없으면 별도재무제표
        try:
            df = dart.finstate_all(corp_code, year, fs_div=fs_div)
        except Exception:
            df = None
        if df is not None and len(df) > 0:
            df = df.copy()
            df["account_nm"] = df["account_nm"].astype(str).str.strip()

            total_assets = get_amount(df, "자산총계")
            gross_profit = get_amount(df, "매출총이익")
            if gross_profit is None:
                revenue = get_amount(df, "매출액") or get_amount(df, "수익(매출액)")
                cogs = get_amount(df, "매출원가")
                if revenue is not None and cogs is not None:
                    gross_profit = revenue - cogs

            if gross_profit is not None and total_assets:
                return gross_profit / total_assets, ("연결" if fs_div == "CFS" else "별도")
    return None, None


def main():
    dart = OpenDartReader(API_KEY)
    universe = get_universe()

    if MAX_STOCKS > 0:
        universe = universe.head(MAX_STOCKS)

    total = len(universe)
    print(f"스캔 대상: {total}개 종목 (기준연도 {YEAR})")

    results = []
    for i, (_, row) in enumerate(universe.iterrows(), start=1):
        stock_code = str(row["Code"]).zfill(6)
        name = row.get("Name", stock_code)

        corp_code, resolved_name = resolve_corp_code(dart.corp_codes, stock_code)
        if not corp_code:
            print(f"[{i}/{total}] {name}({stock_code}) - DART 미등록, 건너뜀")
            continue

        gpa, fs_type = compute_gpa(dart, corp_code, YEAR)
        if gpa is not None:
            results.append(
                {
                    "종목코드": stock_code,
                    "종목명": resolved_name or name,
                    "GP/A": round(gpa, 4),
                    "재무제표": fs_type,
                }
            )
            print(f"[{i}/{total}] {name} -> GP/A={gpa:.4f}")
        else:
            print(f"[{i}/{total}] {name} -> 계산 불가")

        time.sleep(0.2)  # DART 서버 부담을 줄이기 위한 안전장치

    results.sort(key=lambda x: x["GP/A"], reverse=True)
    top100 = results[:100]

    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "scan_year": YEAR,
        "total_scanned": total,
        "total_success": len(results),
        "ranking": top100,
    }

    os.makedirs("data", exist_ok=True)
    with open("data/gpa_ranking.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"완료: {len(results)}/{total}개 종목 계산 성공, 상위 {len(top100)}개 저장")


if __name__ == "__main__":
    main()
