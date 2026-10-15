"""Deal scoring from public prices and tracked history."""
from __future__ import annotations
from datetime import timedelta
from typing import Any
from django.utils import timezone
from .fx import to_gbp_or_zero
from .models import Game, PriceRecord

def _pct_under(current, baseline):
    if current is None or baseline is None or baseline <= 0:
        return None
    return int(round((1-current/baseline)*100))

def _history_stats(game):
    out={"all_time_low":None,"low_90d":None,"average_90d":None,"history_count":0}
    if not game: return out
    cutoff=timezone.now()-timedelta(days=90)
    vals=[]; recent=[]
    for row in PriceRecord.objects.filter(game=game,in_stock=True).only("price","currency","recorded_at"):
        try: value=float(to_gbp_or_zero(row.price,row.currency))
        except Exception: continue
        if value<=0: continue
        vals.append(value)
        if row.recorded_at>=cutoff: recent.append(value)
    if vals:
        out["history_count"]=len(vals); out["all_time_low"]=round(min(vals),2)
    if recent:
        out["low_90d"]=round(min(recent),2); out["average_90d"]=round(sum(recent)/len(recent),2)
    return out

def predict_deal(*,title="",steam_price_gbp=None,steam_discount=None,launch_gbp=None,best_offer_gbp=None,best_offer_kind=None,game:Game|None=None)->dict[str,Any]:
    signals=[]; drop_score=0; buy_score=50
    current=best_offer_gbp or steam_price_gbp
    under_launch=_pct_under(current,launch_gbp)
    if under_launch is not None:
        if under_launch>=50: buy_score+=25; drop_score-=15; signals.append(f"~{under_launch}% under launch reference — historically strong.")
        elif under_launch>=25: buy_score+=12; signals.append(f"~{under_launch}% under launch — solid sale territory.")
        elif under_launch>=10: buy_score+=5; drop_score+=10; signals.append(f"Only ~{under_launch}% under launch — deeper sales often appear later.")
        elif under_launch<0: drop_score+=20; buy_score-=10; signals.append("Above launch reference — double-check edition/region.")
    disc=steam_discount or 0
    if disc>=60: buy_score+=15; drop_score-=10; signals.append(f"Steam shows -{disc}% — major platform sale.")
    elif disc>=30: buy_score+=8; signals.append(f"Steam -{disc}% mid-tier discount.")
    elif disc>0: drop_score+=12; signals.append(f"Steam only -{disc}% — seasonal sales often go deeper.")
    if best_offer_kind=="third-party" and best_offer_gbp and steam_price_gbp:
        gap=steam_price_gbp-best_offer_gbp
        if gap>5: signals.append(f"Keyshop ~£{gap:.2f} cheaper than Steam — weigh risk vs savings."); buy_score-=5

    history=_history_stats(game)
    low=history["all_time_low"]; avg=history["average_90d"]
    if current and low:
        gap=((current-low)/low)*100
        if current<=low+0.01: buy_score+=20; drop_score-=15; signals.append("At the lowest tracked price so far.")
        elif gap<=5: buy_score+=14; drop_score-=8; signals.append(f"Within {gap:.1f}% of the tracked all-time low.")
        elif gap>=40: buy_score-=10; drop_score+=12; signals.append(f"Still {gap:.0f}% above the tracked all-time low.")
    if current and avg:
        vs=((avg-current)/avg)*100
        if vs>=20: buy_score+=8; signals.append(f"About {vs:.0f}% below the 90-day tracked average.")
        elif vs<=-10: buy_score-=6; drop_score+=8; signals.append("Above the 90-day tracked average — waiting may pay off.")

    if game:
        rows=list(PriceRecord.objects.filter(game=game,recorded_at__gte=timezone.now()-timedelta(days=14)).order_by("recorded_at")[:40])
        if len(rows)>=3:
            first=float(to_gbp_or_zero(rows[0].price,rows[0].currency)); last=float(to_gbp_or_zero(rows[-1].price,rows[-1].currency))
            if first>0 and last>0:
                change=(last-first)/first*100
                if change<=-8: buy_score+=10; signals.append(f"Tracked price fell ~{abs(int(change))}% in 2 weeks.")
                elif change>=8: drop_score-=5; signals.append("Tracked price rose recently — may re-discount later.")
                else: drop_score+=5; signals.append("Tracked price mostly flat recently.")
    drop_score=max(0,min(100,drop_score+40)); buy_score=max(0,min(100,buy_score))
    verdict="Buy now — excellent tracked value" if buy_score>=80 else "Good time to buy (heuristic)" if buy_score>=70 else "Reasonable deal — or wait for a deeper sale" if buy_score>=50 else "Likely better to wait for a sale"
    wait_note="Higher chance of a further drop." if drop_score>=65 else "Mixed — further discounts possible but not guaranteed." if drop_score>=45 else "Further big drops less likely from current signals."
    return {"verdict":verdict,"wait_note":wait_note,"buy_score":buy_score,"drop_likelihood":drop_score,"under_launch_pct":under_launch,**history,"signals":signals[:7],"disclaimer":"Heuristic only from public prices and tracked history — not a guarantee. Always confirm on the store before buying."}
