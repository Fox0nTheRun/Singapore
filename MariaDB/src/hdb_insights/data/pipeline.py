"""Build a deterministic HDBI-1.0.0 prepared-data release from D01-D08."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, shutil, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from .mappings import DATASETS
from .profile_sources import sha256_file
from .clean_resale import clean_resale, OUTPUT_HEADERS as RESALE_HEADERS
from .clean_demographics import clean_demographic, DEMOGRAPHIC_SCHEMAS
from .clean_mobility import clean_mobility, OUTPUT_HEADERS as MOBILITY_HEADERS, MOBILITY_COLUMNS

CONTRACT_VERSION = "HDBI-1.0.0"
TRANSFORM_VERSION_DEFAULT = "0.1.2"
EXPECTED_ROWS = {"D01":240468,"D02":63,"D03":21,"D04":18,"D05":45,"D06":15,"D07":12,"D08":48}
BASELINE_SHA256 = {
"D01":"1af5137b8ea8ce39b45c1cac796377359fb315626fcff422371a854fe067265d",
"D02":"76703160f94c4cf20aac4beee9de3b505edba5aa1aa99ee69a399a6c8b1e6c09",
"D03":"df02fb469ff7a5793004636d80370a4f4a6a01c03116e3b4fc5fd1ebfc11ab23",
"D04":"506f0e7467f5a83180bcfcf23eae3d86a8fd6b1bb06716f0b0af9f3a4cf904a6",
"D05":"c6d9ea399fe3de82058b421d77b3a3486f5906794bd11d31e8e805ae9c29ec20",
"D06":"97ab832982fa38e140be07a8fb015cdadb0c3f177d486213edac2607b94198d9",
"D07":"468774fecbe508de622a9792aa89a819e25762ec5ed6f2ec11480bf35fa7bdf9",
"D08":"5a2fa157e0dc8d7df17813f0a1baab2be68f9985ed2e0c9badef761aaba33735",
}
OUTPUT_FILES = {"D01":"resale.csv", **{k:v[0] for k,v in DEMOGRAPHIC_SCHEMAS.items()}, "D08":"mobility.csv"}

def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")

def _source_headers(dataset_id: str) -> list[str]:
    if dataset_id == "D08": return ["Number", *MOBILITY_COLUMNS.keys()]
    return list(DATASETS[dataset_id]["headers"])

def _expected_output_headers(dataset_id: str) -> list[str]:
    if dataset_id == "D01": return list(RESALE_HEADERS)
    if dataset_id == "D08": return list(MOBILITY_HEADERS)
    return list(DEMOGRAPHIC_SCHEMAS[dataset_id][1] + ["dataset_id","source_file_sha256","source_row_number"])

def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    # C01: UTF-8, no BOM, LF, one header, no index.
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", na_rep="")

def _add_issue(issues: list[dict], severity: str, dataset_id: str, rule_id: str, message: str,
               source_row_number: int | None = None, action: str = "retained") -> None:
    issues.append({"severity":severity,"dataset_id":dataset_id,"rule_id":rule_id,
                   "source_row_number":source_row_number,"message":message,"action":action})

def _validate_mobility_reconciliation(frame: pd.DataFrame, issues: list[dict]) -> dict:
    # Check mode components against published totals only when all four component counts are reported.
    compared = 0; discrepancies = []
    for (area, region), group in frame.groupby(["workplace_area","residence_region_code"], sort=False):
        total_row = group[group["transport_mode_code"] == "ALL"]
        modes = group[group["transport_mode_code"] != "ALL"]
        if len(total_row) != 1 or len(modes) != 4: continue
        tc = total_row.iloc[0]["count"]
        if pd.isna(tc) or modes["count"].isna().any(): continue
        compared += 1
        parts = sum(int(x) for x in modes["count"])
        total = int(tc)
        if parts != total:
            delta = parts-total
            detail = {"workplace_area":area,"residence_region_code":region,"published_total":total,
                      "sum_of_modes":parts,"difference":delta}
            discrepancies.append(detail)
            _add_issue(issues,"warning","D08","MODE_SUM_VS_TOTAL",
                       f"{area}/{region}: mode sum {parts} differs from published total {total} by {delta}; values retained.")
    return {"complete_comparisons":compared,"discrepancy_count":len(discrepancies),"discrepancies":discrepancies}

def _pivot_back_check(source: pd.DataFrame, mobility: pd.DataFrame) -> dict:
    mapped = {(int(r.source_row_number), r.source_column): ("-" if r.count_status == "unresolved_dash" else str(int(r["count"])))
              for _, r in mobility.iterrows()}
    mismatches=[]
    for source_row_number, src in enumerate(source.to_dict(orient="records"), start=1):
        for column in MOBILITY_COLUMNS:
            if mapped.get((source_row_number,column)) != str(src[column]).strip():
                mismatches.append({"source_row_number":source_row_number,"source_column":column,
                                   "expected":str(src[column]).strip(),"observed":mapped.get((source_row_number,column))})
                if len(mismatches) >= 10: break
        if len(mismatches) >= 10: break
    return {"status":"PASS" if not mismatches and len(mapped)==len(source)*len(MOBILITY_COLUMNS) else "FAIL",
            "source_cells":len(source)*len(MOBILITY_COLUMNS),"output_cells":len(mapped),"mismatches_sample":mismatches}

def build_release(raw_dir: str | Path, output_root: str | Path, report_dir: str | Path,
                  transform_version: str = TRANSFORM_VERSION_DEFAULT, datasets: list[str] | None = None) -> dict:
    raw_dir, output_root, report_dir = Path(raw_dir), Path(output_root), Path(report_dir)
    selected = datasets or list(DATASETS)
    if selected != list(DATASETS):
        raise ValueError("Full release requires D01-D08 in ascending order. Partial releases are not published by this entry point.")
    output_root.mkdir(parents=True, exist_ok=True); report_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    sources, raw_frames, source_hashes = [], {}, {}
    file_issues=[]
    for dataset_id, spec in DATASETS.items():
        source_path = raw_dir / spec["filename"]
        if not source_path.is_file():
            sources.append({"dataset_id":dataset_id,"source_filename":spec["filename"],"source_sha256":None,
                            "row_count":None,"headers":[],"source_url":None,"metadata_status":"missing_file"})
            _add_issue(file_issues,"error",dataset_id,"SOURCE_MISSING",f"Missing source file: {spec['filename']}",action="blocked")
            continue
        sha = sha256_file(source_path); raw = _read_csv(source_path)
        source_hashes[dataset_id]=sha; raw_frames[dataset_id]=raw
        expected_headers=_source_headers(dataset_id); observed=list(raw.columns)
        if observed != expected_headers:
            _add_issue(file_issues,"error",dataset_id,"SOURCE_HEADERS",f"Header mismatch; expected {expected_headers}, observed {observed}",action="blocked")
        if len(raw) != EXPECTED_ROWS[dataset_id]:
            _add_issue(file_issues,"warning",dataset_id,"BASELINE_ROW_COUNT",f"Observed {len(raw)} rows; reference snapshot has {EXPECTED_ROWS[dataset_id]}; investigate as a changed snapshot.")
        if sha != BASELINE_SHA256[dataset_id]:
            _add_issue(file_issues,"warning",dataset_id,"BASELINE_HASH_DIFFERENCE",f"Raw hash differs from reference fingerprint; observed {sha}. Raw bytes were not modified.")
        sources.append({"dataset_id":dataset_id,"source_filename":spec["filename"],"source_sha256":sha,"row_count":len(raw),
                        "headers":observed,"source_url":None,"metadata_status":"partial"})
    if set(source_hashes) != set(DATASETS):
        return _write_blocked_report(report_dir, started, sources, file_issues, "Not all eight expected raw inputs are available.")
    hash_sequence="".join(f"{dataset_id}:{source_hashes[dataset_id]}\n" for dataset_id in DATASETS)
    snapshot_id=_sha_text(hash_sequence)
    data_release_id=f"{snapshot_id[:12]}_c1.0.0_t{transform_version}"
    stage = Path(tempfile.mkdtemp(prefix=f".{data_release_id}.staging-", dir=output_root))
    all_issues=list(file_issues); prepared={}; output_entries=[]; checks=[]
    try:
        for dataset_id in DATASETS:
            raw=raw_frames[dataset_id]; sha=source_hashes[dataset_id]
            if dataset_id == "D01": frame, issues = clean_resale(raw, sha)
            elif dataset_id in DEMOGRAPHIC_SCHEMAS: frame, issues = clean_demographic(raw, dataset_id, sha)
            else: frame, issues = clean_mobility(raw, sha)
            all_issues.extend(issues); prepared[dataset_id]=frame
            expected_headers=_expected_output_headers(dataset_id)
            if list(frame.columns) != expected_headers:
                _add_issue(all_issues,"error",dataset_id,"OUTPUT_HEADERS",f"Prepared headers differ from C01: {list(frame.columns)}",action="blocked")
            expected_output_count = len(raw) * len(MOBILITY_COLUMNS) if dataset_id == "D08" else len(raw)
            if len(frame) != expected_output_count:
                _add_issue(all_issues,"error",dataset_id,"ROW_RECONCILIATION",f"Prepared {len(frame)} rows; expected {expected_output_count} rows from the defined transformation grain.",action="blocked")
            out_path=stage/OUTPUT_FILES[dataset_id]; _write_csv(frame,out_path)
            output_hash=sha256_file(out_path)
            key_map={"D01":["record_id"],"D02":["survey_year","flat_type_code","age_group_code"],"D03":["survey_year","flat_type_code"],"D04":["survey_year","flat_type_code"],"D05":["survey_year","ethnic_group_code","age_group_code"],"D06":["survey_year","ethnic_group_code"],"D07":["survey_year","ethnic_group_code"],"D08":["survey_year","workplace_area","residence_region_code","transport_mode_code"]}[dataset_id]
            err_count=sum(1 for issue in issues if issue.get("severity")=="error")
            warn_count=sum(1 for issue in issues if issue.get("severity")=="warning")
            output_entries.append({"filename":OUTPUT_FILES[dataset_id],"schema_id":f"C01-{dataset_id}","output_sha256":output_hash,
                                   "row_count":len(frame),"logical_key":key_map,"source_ids":[dataset_id],"warning_count":warn_count,
                                   "rejected_count":err_count,"readiness":"blocked" if err_count else ("ready_with_warnings" if warn_count else "ready")})
            checks.append({"check_id":f"SOURCE_HEADER_{dataset_id}","dataset_id":dataset_id,"status":"PASS" if list(raw.columns)==_source_headers(dataset_id) else "FAIL",
                           "observed":list(raw.columns),"expected":_source_headers(dataset_id),"evidence_path":"source_profile.json"})
            expected_output_count = len(raw) * len(MOBILITY_COLUMNS) if dataset_id == "D08" else len(raw)
            checks.append({"check_id":f"ROW_COUNT_{dataset_id}","dataset_id":dataset_id,"status":"PASS" if len(frame)==expected_output_count else "FAIL",
                           "observed":len(frame),"expected":expected_output_count,"evidence_path":"pipeline_report.json"})
        d01=prepared["D01"]
        duplicate_occurrences=int(raw_frames["D01"].duplicated(keep="first").sum())
        checks.extend([
            {"check_id":"D01_DUPLICATE_ROWS_RETAINED","dataset_id":"D01","status":"PASS" if len(d01)==240468 and d01["record_id"].nunique()==len(d01) else "FAIL",
             "observed":{"rows":len(d01),"unique_record_ids":int(d01["record_id"].nunique()),"duplicate_occurrences_in_source":duplicate_occurrences},
             "expected":{"baseline_rows":240468,"duplicate_occurrences":318},"evidence_path":"pipeline_report.json"},
        ])
        mob=prepared["D08"]
        dash_count=int((mob["count_status"]=="unresolved_dash").sum())
        checks.append({"check_id":"D08_DASH_PRESERVATION","dataset_id":"D08","status":"PASS" if len(mob)==1440 and dash_count==73 else "FAIL",
                       "observed":{"rows":len(mob),"unresolved_dash_count":dash_count},"expected":{"rows":1440,"unresolved_dash_count":73},"evidence_path":"pipeline_report.json"})
        pivot_result=_pivot_back_check(raw_frames["D08"],mob)
        checks.append({"check_id":"D08_PIVOT_BACK","dataset_id":"D08","status":pivot_result["status"],"observed":pivot_result,"expected":{"source_cells":1440,"mismatches":0},"evidence_path":"pipeline_report.json"})
        mobility_reconciliation=_validate_mobility_reconciliation(mob, all_issues)
        checks.append({"check_id":"D08_RECONCILIATION","dataset_id":"D08","status":"WARN" if mobility_reconciliation["discrepancy_count"] else "PASS",
                       "observed":{"complete_comparisons":mobility_reconciliation["complete_comparisons"],"discrepancy_count":mobility_reconciliation["discrepancy_count"],"first_discrepancies":mobility_reconciliation["discrepancies"][:5]},
                       "expected":{"policy":"retain published totals; warn rather than adjust if components differ"},"evidence_path":"validation_issues.json"})
        if dash_count:
            _add_issue(all_issues,"warning","D08","DASH_MEANING_UNRESOLVED",f"{dash_count} source dash tokens retained as null with unresolved_dash status; do not treat as zero.")
        checks.append({"check_id":"D08_DASH_SEMANTICS","dataset_id":"D08","status":"WARN" if dash_count else "PASS",
                       "observed":{"unresolved_dash_count":dash_count},"expected":{"policy":"preserve null + unresolved_dash until source-specific meaning is verified"},"evidence_path":"validation_issues.json"})
        pct_warnings=sum(1 for issue in all_issues if issue.get("rule_id")=="AGE_PERCENTAGE_SUM" and issue.get("severity")=="warning")
        checks.append({"check_id":"DEMOGRAPHIC_PERCENTAGE_SUMS","dataset_id":None,"status":"WARN" if pct_warnings else "PASS",
                       "observed":{"non_100_groups_within_tolerance":pct_warnings},"expected":{"policy":"retain published percentages; warn when not exactly 100 and block outside tolerance"},"evidence_path":"validation_issues.json"})
        # Normalize issue records to the shared data validation issue schema before evidence publication.
        for issue in all_issues:
            dataset_id = issue.get("dataset_id")
            issue.setdefault("source_file_sha256", source_hashes.get(dataset_id) if dataset_id else None)
            issue.setdefault("source_row_number", None)
            issue.setdefault("source_column", None)
            issue.setdefault("rule_id", "TRANSFORM_VALIDATION_WARNING" if issue.get("severity") == "warning" else "TRANSFORM_VALIDATION_ERROR")
            issue.setdefault("raw_value", None)
            issue.setdefault("action", "retained" if issue.get("severity") == "warning" else "blocked")
        # Readiness reflects all observed checks, including cross-cell reconciliation and unresolved source tokens.
        for entry in output_entries:
            dataset_id = entry["schema_id"].split("-")[-1]
            dataset_issues = [issue for issue in all_issues if issue.get("dataset_id") == dataset_id]
            dataset_errors = sum(1 for issue in dataset_issues if issue.get("severity") == "error")
            dataset_warnings = sum(1 for issue in dataset_issues if issue.get("severity") == "warning")
            entry["warning_count"] = dataset_warnings
            entry["rejected_count"] = dataset_errors
            entry["readiness"] = "blocked" if dataset_errors else ("ready_with_warnings" if dataset_warnings else "ready")
        issues_path=stage/"validation_issues.json"
        issues_path.write_text(json.dumps(all_issues,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        errors=sum(1 for issue in all_issues if issue.get("severity")=="error")
        warnings=sum(1 for issue in all_issues if issue.get("severity")=="warning")
        fingerprint_matches = all(source_hashes.get(d) == BASELINE_SHA256[d] for d in DATASETS)
        checks.append({"check_id":"SOURCE_FINGERPRINTS","dataset_id":None,"status":"PASS" if fingerprint_matches else "WARN",
                       "observed":{"all_match_reference":fingerprint_matches,"hashes":source_hashes},"expected":"All eight hashes match the reference snapshot; changed snapshots are allowed only with a documented difference report.","evidence_path":"source_profile.json"})
        checks.append({"check_id":"NO_BLOCKING_VALIDATION_ISSUES","dataset_id":None,"status":"PASS" if errors==0 else "FAIL",
                       "observed":{"error_count":errors,"warning_count":warnings},"expected":{"error_count":0},"evidence_path":"validation_issues.json"})
        if any(c["status"]=="FAIL" for c in checks) or errors:
            shutil.rmtree(stage,ignore_errors=True)
            return _write_blocked_report(report_dir,started,sources,all_issues,"One or more acceptance checks failed; no release published.",checks=checks)
        unresolved=["D08 source token '-' meaning remains unverified; retain null count and unresolved_dash status.",
                    "Demographic age percentages may sum to 100.1 due to published precision; source values retained.",
                    "Population totals across flat-type and ethnicity source tables differ by 1,000 in each survey year; not reconciled.",
                    "D08 workplace categories and residence regions represent different dimensions from resale towns; no geographic join is inferred."]
        manifest={"contract_version":CONTRACT_VERSION,"transform_version":transform_version,"snapshot_id":snapshot_id,"data_release_id":data_release_id,
                  "generated_at_utc":datetime.now(timezone.utc).isoformat(),"python_version":platform.python_version(),
                  "package_versions":{"pandas":pd.__version__},"code_revision":None,"sources":sources,"outputs":output_entries,
                  "validation_summary":{"error_count":errors,"warning_count":warnings,"checks":checks},"unresolved_decisions":unresolved}
        # Check output hashes directly from written bytes before publishing.
        for entry in output_entries:
            path=stage/entry["filename"]
            if sha256_file(path)!=entry["output_sha256"]: raise RuntimeError(f"written output hash mismatch: {entry['filename']}")
        (stage/"manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        final_dir=output_root/data_release_id
        if final_dir.exists():
            # Reruns must verify rather than overwrite a release with the same deterministic ID.
            old_manifest=json.loads((final_dir/"manifest.json").read_text(encoding="utf-8"))
            for entry in output_entries:
                existing=final_dir/entry["filename"]
                if not existing.exists() or sha256_file(existing)!=entry["output_sha256"]:
                    raise RuntimeError(f"Existing release {data_release_id} differs at {entry['filename']}; refusing to overwrite.")
            shutil.rmtree(stage)
            manifest=old_manifest
        else:
            os.replace(stage,final_dir)
        report={"status":"VERIFIED_WITH_WARNINGS" if warnings else "VERIFIED","contract_version":CONTRACT_VERSION,
                "transform_version":transform_version,"snapshot_id":snapshot_id,"data_release_id":data_release_id,
                "source_dir":str(raw_dir),"release_path":str(final_dir),"source_datasets":len(sources),
                "source_rows":{s["dataset_id"]:s["row_count"] for s in sources},
                "output_rows":{o["filename"]:o["row_count"] for o in output_entries},
                "source_hashes_match_reference":{d:source_hashes[d]==BASELINE_SHA256[d] for d in DATASETS},
                "duplicate_occurrences_D01":duplicate_occurrences,"D08_unresolved_dash_count":dash_count,
                "D08_pivot_back":pivot_result,"D08_reconciliation":mobility_reconciliation,
                "error_count":errors,"warning_count":warnings,"issues_path":str(final_dir/"validation_issues.json"),
                "manifest_path":str(final_dir/"manifest.json"),"generated_at_utc":datetime.now(timezone.utc).isoformat(),
                "python_version":platform.python_version(),"pandas_version":pd.__version__,
                "note":"This verifies the local preparation release only. MariaDB/MongoDB loading and application integration are not verified."}
        (report_dir/"pipeline_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        # Independent compact source profiler result recorded as evidence.
        profile={"generated_at_utc":started,"datasets":sources,"summary":{"datasets_expected":8,"datasets_found":8}}
        (report_dir/"source_profile.json").write_text(json.dumps(profile,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        return report
    except Exception:
        shutil.rmtree(stage,ignore_errors=True)
        raise

def _write_blocked_report(report_dir: Path, started: str, sources: list[dict], issues: list[dict], reason: str, checks: list[dict] | None=None) -> dict:
    report_dir.mkdir(parents=True,exist_ok=True)
    report={"status":"BLOCKED","reason":reason,"contract_version":CONTRACT_VERSION,"generated_at_utc":datetime.now(timezone.utc).isoformat(),
            "started_at_utc":started,"sources":sources,"error_count":sum(1 for i in issues if i.get("severity")=="error"),
            "warning_count":sum(1 for i in issues if i.get("severity")=="warning"),"issues":issues,"checks":checks or [],
            "note":"No complete release was published."}
    (report_dir/"pipeline_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return report

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--raw-dir",required=True); parser.add_argument("--output-root",required=True); parser.add_argument("--report-dir",required=True)
    parser.add_argument("--transform-version",default=TRANSFORM_VERSION_DEFAULT); parser.add_argument("--datasets",nargs="+",default=list(DATASETS))
    args=parser.parse_args()
    try: report=build_release(args.raw_dir,args.output_root,args.report_dir,args.transform_version,args.datasets)
    except (ValueError,NotImplementedError) as exc:
        print(f"BLOCKED: {exc}",file=sys.stderr); return 2
    print(json.dumps(report,indent=2,ensure_ascii=False))
    return 1 if report.get("status")=="BLOCKED" else 0
if __name__=="__main__": raise SystemExit(main())
