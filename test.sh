# python tools/hdc/generate.py 65938636 dw_onedba     --namespace recall_extra     --tables "order_task_log,account_whitelist,db_alert_current_history,db_ecs_disks,db_dms_nddl,account, order_record,db_alert_history,effect_dba_domain_cost_v2,effect_alert_v2,effect_daily_work_v2,order_audit_record,db_act_whitelist,account_orgstructure,db_alert_daily,order_report_day,effect_daily_work_type_v2" -v

# python tools/hdc/generate.py 65938636 dw_onedba     --namespace recall_complete     --tables "order_record,db_alert_history,effect_dba_domain_cost_v2,effect_daily_work_v2,order_audit_record" -v


rep=20
conc=6
ids="TC-005"
a="TC-003 TC-015 TC-017 TC-029 TC-027"

cmd="python -u -m tests.evaluation.cli run --compare-sql-memory --with-hdc  --skip-seed --skip-baseline  --baseline /Users/admin/DBR/DB-Agent/Infra-DB-Agent/DBAgent/tests/output/incremental_hdc_eval/01-noHDC-2.json  --verbose --verbose-hdc --repeat $rep --concurrency $conc"

# $cmd  2>&1 | tee HDCno.log



$cmd --hdc-namespace recall_complete 2>&1 | tee HDCcomplete_eval.log

$cmd --hdc-namespace recall_extra 2>&1 | tee HDCextra_eval.log