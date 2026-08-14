"""
전체 상장 종목 GP/A + PBR 자동 스캔 스크립트
GitHub Actions가 매일 이 스크립트를 실행해서 data/gpa_ranking.json 을 만듭니다.
Streamlit 앱(app.py)은 이 파일을 그냥 읽기만 하므로, 사이트 접속 시 대기시간이 없습니다.

v2: 종목을 동시에(병렬로) 조회하도록 변경 — 순차 처리 시 2,500개에 약 10시간이 걸려
GitHub Actions 제한(6시간)을 초과하는 문제를 해결하기 위함입니다.

v3: PBR 추가. 시가총액(FinanceDataReader) × 자본총계(이미 조회한 재무제표에 포함)로
계산하므로 API 호출이 추가되지 않습니다. 최종 순위는 원본 설계 의도대로
'GP/A 상위 30% 중 PBR이 낮은 순'으로 뽑습니다(저PBR의 함정을 GP/A로 걸러내는 방식).
"""
import os
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import FinanceDataReader as fdr

try:
    from opendartreader import OpenDartReader
except ImportError:
    import OpenDartReader

API_KEY = os.environ["DART_API_KEY"]
MAX_STOCKS = int(os.environ.get("MAX_STOCKS", "0"))  # 0이면 전체 스캔, 테스트할 땐 30 등으로 제한
YEAR = int(os.environ.get("SCAN_YEAR", str(datetime.today().year - 1)))
WORKERS = int(os.environ.get("SCAN_WORKERS", "5"))  # 동시에 처리할 종목 수
GPA_PERCENTILE = float(os.environ.get("GPA_PERCENTILE", "0.3"))  # GP/A 상위 몇 %까지 '우량주 후보'로 볼지


def get_universe() -> pd.DataFrame:
    """코스피+코스닥 전체 종목 목록(시가총액 포함)을 가져오고, 관리종목은 제외합니다."""
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


def compute_financials(dart, corp_code: str, year: int):
    """같은 재무제표 조회 한 번으로 GP/A 계산에 필요한 값과 PBR 계산에 필요한 자본총계를 함께 뽑는다."""
    for fs_div in ("CFS", "OFS"):  # 연결재무제표 먼저, 없으면 별도재무제표
        try:
            df = dart.finstate_all(corp_code, year, fs_div=fs_div)
        except Exception:
            df = None
        if df is not None and len(df) > 0:
            df = df.copy()
            df["account_nm"] = df["account_nm"].astype(str).str.strip()

            total_assets = get_amount(df, "자산총계")
            equity = get_amount(df, "자본총계")  # PBR 계산용 (추가 API 호출 없음)
            gross_profit = get_amount(df, "매출총이익")
            if gross_profit is None:
                revenue = get_amount(df, "매출액") or get_amount(df, "수익(매출액)")
                cogs = get_amount(df, "매출원가")
                if revenue is not None and cogs is not None:
                    gross_profit = revenue - cogs

            if gross_profit is not None and total_assets:
                gpa = gross_profit / total_assets
                fs_type = "연결" if fs_div == "CFS" else "별도"
                return gpa, equity, fs_type
    return None, None, None


def get_account_set(dart, corp_code: str, year: int):
    """F-Score 계산에 필요한 여러 재무 계정을 한 해 기준으로 한 번에 뽑는다."""
    for fs_div in ("CFS", "OFS"):
        try:
            df = dart.finstate_all(corp_code, year, fs_div=fs_div)
        except Exception:
            df = None
        if df is not None and len(df) > 0:
            df = df.copy()
            df["account_nm"] = df["account_nm"].astype(str).str.strip()

            revenue = get_amount(df, "매출액") or get_amount(df, "수익(매출액)")
            gross_profit = get_amount(df, "매출총이익")
            cogs = get_amount(df, "매출원가")
            if gross_profit is None and revenue is not None and cogs is not None:
                gross_profit = revenue - cogs
            cfo = get_amount(df, "영업활동으로인한현금흐름") or get_amount(df, "영업활동현금흐름")

            return {
                "total_assets": get_amount(df, "자산총계"),
                "liabilities": get_amount(df, "부채총계"),
                "current_assets": get_amount(df, "유동자산"),
                "current_liabilities": get_amount(df, "유동부채"),
                "capital_stock": get_amount(df, "자본금"),
                "net_income": get_amount(df, "당기순이익"),
                "cfo": cfo,
                "revenue": revenue,
                "gross_profit": gross_profit,
            }
    return None


def _safe_div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def compute_fscore(cur, prev):
    """피오트로스키 F-Score. 9점 만점, 데이터가 없어 계산 불가능한 항목은 0점 처리하고
    실제로 몇 개 항목을 채점했는지(checkable)도 함께 반환한다."""
    if cur is None:
        return 0, 0

    score = 0
    checkable = 0
    prev = prev or {}

    roa_cur = _safe_div(cur.get("net_income"), cur.get("total_assets"))
    roa_prev = _safe_div(prev.get("net_income"), prev.get("total_assets"))

    checks = []
    # 1. ROA > 0
    checks.append((roa_cur is not None, roa_cur is not None and roa_cur > 0))
    # 2. CFO > 0
    checks.append((cur.get("cfo") is not None, cur.get("cfo") is not None and cur["cfo"] > 0))
    # 3. ΔROA > 0
    checks.append((roa_cur is not None and roa_prev is not None, roa_cur is not None and roa_prev is not None and roa_cur > roa_prev))
    # 4. CFO > 당기순이익 (이익의 질)
    ok4 = cur.get("cfo") is not None and cur.get("net_income") is not None
    checks.append((ok4, ok4 and cur["cfo"] > cur["net_income"]))
    # 5. 부채비율(부채/자산총계) 감소
    lev_cur = _safe_div(cur.get("liabilities"), cur.get("total_assets"))
    lev_prev = _safe_div(prev.get("liabilities"), prev.get("total_assets"))
    ok5 = lev_cur is not None and lev_prev is not None
    checks.append((ok5, ok5 and lev_cur < lev_prev))
    # 6. 유동비율(유동자산/유동부채) 증가
    cr_cur = _safe_div(cur.get("current_assets"), cur.get("current_liabilities"))
    cr_prev = _safe_div(prev.get("current_assets"), prev.get("current_liabilities"))
    ok6 = cr_cur is not None and cr_prev is not None
    checks.append((ok6, ok6 and cr_cur > cr_prev))
    # 7. 신주 발행 없음 (자본금 증가 없음 = 희석 없음)
    ok7 = cur.get("capital_stock") is not None and prev.get("capital_stock") is not None
    checks.append((ok7, ok7 and cur["capital_stock"] <= prev["capital_stock"]))
    # 8. 매출총이익률 증가
    gpm_cur = _safe_div(cur.get("gross_profit"), cur.get("revenue"))
    gpm_prev = _safe_div(prev.get("gross_profit"), prev.get("revenue"))
    ok8 = gpm_cur is not None and gpm_prev is not None
    checks.append((ok8, ok8 and gpm_cur > gpm_prev))
    # 9. 자산회전율(매출액/자산총계) 증가
    turn_cur = _safe_div(cur.get("revenue"), cur.get("total_assets"))
    turn_prev = _safe_div(prev.get("revenue"), prev.get("total_assets"))
    ok9 = turn_cur is not None and turn_prev is not None
    checks.append((ok9, ok9 and turn_cur > turn_prev))

    for is_checkable, passed in checks:
        if is_checkable:
            checkable += 1
            if passed:
                score += 1

    return score, checkable


def compute_fscore_for_stock(dart, stock_code: str, year: int):
    matched = dart.corp_codes[dart.corp_codes["stock_code"] == stock_code]
    if matched.empty:
        return 0, 0
    corp_code = matched.iloc[0]["corp_code"]
    cur = get_account_set(dart, corp_code, year)
    prev = get_account_set(dart, corp_code, year - 1)
    return compute_fscore(cur, prev)


def scan_one(dart, stock_code: str, name: str, year: int, marcap):
    corp_code, resolved_name = resolve_corp_code(dart.corp_codes, stock_code)
    if not corp_code:
        return None
    gpa, equity, fs_type = compute_financials(dart, corp_code, year)
    if gpa is None:
        return None

    pbr = None
    if equity and equity > 0 and marcap:
        try:
            pbr = float(marcap) / equity
        except (TypeError, ValueError):
            pbr = None

    return {
        "종목코드": stock_code,
        "종목명": resolved_name or name,
        "GP/A": round(gpa, 4),
        "PBR": round(pbr, 2) if pbr is not None else None,
        "재무제표": fs_type,
    }


def build_ranking(results):
    """원본 설계 의도: GP/A 상위 X% (우량주 후보) 중에서 PBR이 낮은 순으로 최종 100개를 뽑는다."""
    valid = [r for r in results if r["GP/A"] is not None]
    valid.sort(key=lambda x: x["GP/A"], reverse=True)

    cutoff = max(1, int(len(valid) * GPA_PERCENTILE))
    quality_pool = valid[:cutoff]  # GP/A 상위 X% = '알짜 기업' 후보군

    with_pbr = [r for r in quality_pool if r["PBR"] is not None]
    without_pbr = [r for r in quality_pool if r["PBR"] is None]
    with_pbr.sort(key=lambda x: x["PBR"])  # 저PBR(싼 순)부터

    return (with_pbr + without_pbr)[:100]


def save_results(results, total, year, complete):
    ranking = build_ranking(results)
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "scan_year": year,
        "total_scanned": total,
        "total_success": len([r for r in results if r["GP/A"] is not None]),
        "complete": complete,  # False면 중간 저장본(스캔이 끝까지 못 갔을 수 있음)
        "filter_note": f"GP/A 상위 {int(GPA_PERCENTILE*100)}% 중 PBR 낮은 순",
        "ranking": ranking,
    }
    os.makedirs("data", exist_ok=True)
    with open("data/gpa_ranking.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


CHECKPOINT_EVERY = 200  # 이만큼 처리할 때마다 중간 저장 (중간에 실패해도 결과가 남도록)
F_SCORE_THRESHOLD = int(os.environ.get("F_SCORE_THRESHOLD", "7"))  # 9점 만점 중 몇 점 이상을 통과로 볼지
F_SCORE_POOL_SIZE = int(os.environ.get("F_SCORE_POOL_SIZE", "100"))  # GP/A 상위 몇 개에 F-Score를 적용할지


def main():
    start_time = time.time()
    dart = OpenDartReader(API_KEY)
    universe = get_universe()

    if MAX_STOCKS > 0:
        universe = universe.head(MAX_STOCKS)

    total = len(universe)
    print(f"[1단계] 스캔 대상: {total}개 종목 (기준연도 {YEAR}, 동시 처리 {WORKERS}개)")

    # ---------------- 1단계: 전체 종목 GP/A + PBR 스캔 ----------------
    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {}
        for _, row in universe.iterrows():
            stock_code = str(row["Code"]).zfill(6)
            name = row.get("Name", stock_code)
            marcap = row.get("Marcap")
            fut = executor.submit(scan_one, dart, stock_code, name, YEAR, marcap)
            futures[fut] = name

        for fut in as_completed(futures):
            done += 1
            name = futures[fut]
            try:
                result = fut.result()
            except Exception as e:
                print(f"[{done}/{total}] {name} -> 오류: {e}")
                continue
            if result:
                results.append(result)
                pbr_txt = f"{result['PBR']}" if result["PBR"] is not None else "N/A"
                print(f"[{done}/{total}] {result['종목명']} -> GP/A={result['GP/A']:.4f}, PBR={pbr_txt}")
            else:
                print(f"[{done}/{total}] {name} -> 계산 불가")

            if done % CHECKPOINT_EVERY == 0:
                save_results(results, total, YEAR, complete=False)
                print(f"--- 1단계 중간 저장 완료 ({done}/{total}) ---")

    valid = [r for r in results if r["GP/A"] is not None]
    print(f"[1단계 완료] {len(valid)}/{total}개 종목 GP/A 계산 성공 ({(time.time()-start_time)/60:.1f}분 경과)")

    # ---------------- 2단계: GP/A 상위 종목에만 F-Score 계산 ----------------
    valid.sort(key=lambda x: x["GP/A"], reverse=True)
    top_pool = valid[:F_SCORE_POOL_SIZE]
    print(f"[2단계] F-Score 계산 대상: {len(top_pool)}개 (GP/A 상위)")

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(compute_fscore_for_stock, dart, r["종목코드"], YEAR): r for r in top_pool
        }
        done2 = 0
        for fut in as_completed(futures):
            done2 += 1
            r = futures[fut]
            try:
                fscore, checkable = fut.result()
            except Exception as e:
                fscore, checkable = 0, 0
                print(f"[F-Score {done2}/{len(top_pool)}] {r['종목명']} -> 오류: {e}")
            r["F-Score"] = fscore
            r["F-Score 항목수"] = checkable
            print(f"[F-Score {done2}/{len(top_pool)}] {r['종목명']} -> {fscore}/9점 (평가 가능 {checkable}개)")

    # ---------------- 3단계: F-Score 통과 종목만 PBR 낮은 순으로 최종 정렬 ----------------
    passed = [r for r in top_pool if r.get("F-Score", 0) >= F_SCORE_THRESHOLD]
    with_pbr = [r for r in passed if r["PBR"] is not None]
    without_pbr = [r for r in passed if r["PBR"] is None]
    with_pbr.sort(key=lambda x: x["PBR"])
    final_ranking = with_pbr + without_pbr

    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "scan_year": YEAR,
        "total_scanned": total,
        "total_success": len(valid),
        "fscore_pool_size": len(top_pool),
        "fscore_threshold": F_SCORE_THRESHOLD,
        "fscore_passed": len(passed),
        "complete": True,
        "filter_note": f"GP/A 상위 {len(top_pool)}개 → F-Score {F_SCORE_THRESHOLD}점 이상 → PBR 낮은 순",
        "ranking": final_ranking,
    }
    os.makedirs("data", exist_ok=True)
    with open("data/gpa_ranking.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time
    print(f"완료: GP/A 성공 {len(valid)}개 → F-Score {F_SCORE_THRESHOLD}점 이상 통과 {len(passed)}개")
    print(f"총 소요시간: {elapsed/60:.1f}분")


if __name__ == "__main__":
    main()
