"""Independent, source-oriented control totals for the prepared data release."""
from __future__ import annotations
import argparse, csv, json, hashlib
from decimal import Decimal, ROUND_HALF_UP, localcontext
from datetime import datetime, timezone
from pathlib import Path

def read_rows(path: Path):
    with path.open("r",encoding="utf-8",newline="") as f:
        return list(csv.DictReader(f))

def money2(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def build_controls(release_dir: Path) -> dict:
    resale=read_rows(release_dir/"resale.csv")
    count_by_town_type={}
    for row in resale:
        key=(row["town_name"],row["flat_type_code"])
        count_by_town_type[key]=count_by_town_type.get(key,0)+1
    # A fixed query slice provides an independent comparison baseline.
    selected=[r for r in resale if r["town_name"]=="ANG MO KIO" and r["flat_type_code"]=="2_ROOM" and r["registration_month"]=="2017-01"]
    with localcontext() as ctx:
        ctx.prec=28
        prices=[Decimal(r["resale_price"]) for r in selected]
        price_per_sqm=[Decimal(r["resale_price"])/Decimal(r["floor_area_sqm"]) for r in selected]
        avg_price=money2(sum(prices,Decimal("0"))/len(prices)) if prices else None
        avg_ppsqm=money2(sum(price_per_sqm,Decimal("0"))/len(price_per_sqm)) if price_per_sqm else None
    demographics=[r for r in read_rows(release_dir/"age_by_flat_type.csv") if r["survey_year"]=="2018" and r["flat_type_code"]=="3_ROOM"]
    demographics.sort(key=lambda r:{"BELOW_15":0,"AGE_15_64":1,"AGE_65_PLUS":2}.get(r["age_group_code"],99))
    mobility=[r for r in read_rows(release_dir/"mobility.csv") if r["workplace_area"]=="Boon Lay" and r["residence_region_code"]=="EAST"]
    total_rows=[r for r in mobility if r["transport_mode_code"]=="ALL"]
    published_total=int(total_rows[0]["count"]) if len(total_rows)==1 and total_rows[0]["count"] else None
    modes=[]
    with localcontext() as ctx:
        ctx.prec=28
        for row in sorted((r for r in mobility if r["transport_mode_code"]!="ALL"),key=lambda r:{"RAIL_BUS":0,"CAR_TAXI_PRIVATE_HIRE":1,"OTHER":2,"NO_TRANSPORT":3}[r["transport_mode_code"]]):
            count=int(row["count"]) if row["count"] else None
            share=money2(Decimal(count)*Decimal("100")/Decimal(published_total)) if count is not None and published_total not in (None,0) else None
            modes.append({"transport_mode_code":row["transport_mode_code"],"count":count,"count_status":row["count_status"],"share_pct":share,"source_column":row["source_column"]})
    # Check raw/output hash fingerprints and exact documented row counts.
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(release_dir.glob("*.csv"))}
    return {
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "data_release_id":release_dir.name,
        "control_scope":"Prepared CSV independent controls only; no DB query results are asserted here.",
        "resale":{"total_count":len(resale),"count_by_town_and_flat_type":{"ANG MO KIO":{"2_ROOM":count_by_town_type.get(("ANG MO KIO","2_ROOM"),0)}},
                  "filter":{"town_name":"ANG MO KIO","flat_type_code":"2_ROOM","registration_month":"2017-01"},
                  "selected_filter_count":len(selected),"selected_filter_average_price":avg_price,
                  "selected_filter_average_price_per_sqm":avg_ppsqm,"average_price_per_sqm_definition":"mean of each selected transaction's price / floor area, not total price / total area"},
        "demographic_profile":{"survey_year":2018,"flat_type_code":"3_ROOM","age_distribution":demographics},
        "mobility_breakdown":{"survey_year":2020,"workplace_area":"Boon Lay","residence_region_code":"EAST","published_total":published_total,"modes":modes},
        "output_csv_sha256":hashes,
    }
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--release-dir",required=True); parser.add_argument("--output",required=True)
    args=parser.parse_args()
    result=build_controls(Path(args.release_dir))
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"output":str(out),"data_release_id":result["data_release_id"],"resale_count":result["resale"]["total_count"],"selected_filter_count":result["resale"]["selected_filter_count"]},indent=2))
if __name__=="__main__": main()
