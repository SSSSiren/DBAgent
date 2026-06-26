# OneDBA Schema 详细摘要

- 数据库: dw_onedba @ dw-onedba-t1
- Schema ID: 65938636
- 总表数: 537
- 已拉取详情: 108 张表

---

## db_act_cleankeys (约 4 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| order_id | bigint | NO | MUL | 0 |  |
| order_type | varchar(200) | NO |  |  |  |
| mainbody | varchar(200) | NO |  |  |  |
| region_id | varchar(200) | NO |  |  |  |
| db_instance_id | varchar(200) | NO |  |  |  |
| key_prefix | longtext | YES |  | NULL |  |
| db_instance_type | varchar(20) | NO |  |  |  |
| aliyun_token | varchar(200) | NO |  |  |  |
| db | int | NO |  | 0 |  |
| clean_type | varchar(200) | NO |  | prefix |  |
| committer_name | varchar(200) | NO |  | 0 |  |
| job_status | varchar(200) | NO |  | 0 |  |
| comment | text | YES |  | NULL |  |
| commit_user_id | varchar(200) | NO |  |  |  |
| finished_time | timestamp | YES |  | NULL |  |
| gmt_create | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| gmt_modify | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| last_execute_time | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| is_parallel | tinyint | NO |  | 1 |  |
| process_rate | int | NO |  | 0 |  |
| uuid | varchar(200) | NO |  |  |  |

**样例数据:**

| id | db | clean_type | committer_name | job_status | comment | commit_user_id | finished_time | gmt_create | gmt_modify | last_execute_time | order_id | is_parallel | process_rate | uuid | order_type | mainbody | region_id | db_instance_id | key_prefix | db_instance_type | aliyun_token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 7 | 0 | prefix | 0 | 1 | 0 |  | NULL | 2022-01-11 21:54:29 | 2022-01-18 16:58:33 | 2022-01-18 16:58:33 | 1211212 | 0 | 0 |  | cleanKeys | shizhuang | cn-shanghai | r-uf65s3orupmfwx7dal | Csong | acs_kvstore | r-uf65s3orupmfwx7dal |
| 8 | 0 | prefixMatch |  | 1 | 1 | 3081 | 2023-03-16 01:53:52 | 2023-03-16 01:35:57 | 2023-03-16 01:35:57 | 2023-03-16 01:45:47 | 20016 | 1 | 0 |  | cleanKey | shizhuang | cn-shanghai | r-uf6w4jeitf13wkzgj8 | csong | acs_kvstore | 512158dc-81e5-4230-9473-e16fbeb677df |
| 9 | 0 | prefixMatch |  | 1 | 52 | 3081 | 2023-03-16 02:24:17 | 2023-03-16 02:17:13 | 2023-03-16 02:17:13 | 2023-03-16 02:17:15 | 20020 | 1 | 0 |  | cleanKey | shizhuang | cn-shanghai | r-uf6w4jeitf13wkzgj8 | csong,chensong,chen,song | acs_kvstore | d5889fa5-4169-402c-a179-450755ba47ae |

---

## db_act_data_archive_group (约 16 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| order_id | bigint | NO | MUL | 0 |  |
| publish_group_id | bigint | NO |  | 0 |  |
| publish_number | int | NO |  | 0 |  |
| is_transaction | tinyint(1) | NO |  | 0 |  |
| last_execute_time | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| finished_time | timestamp | YES |  | NULL |  |
| creator_name | varchar(200) | NO |  |  |  |
| creator_id | varchar(200) | NO |  |  |  |
| job_status | tinyint | NO |  | 0 |  |
| comment | mediumtext | YES |  | NULL |  |
| gmt_create | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| gmt_modify | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| config | longtext | YES |  | NULL |  |

**样例数据:**

| id | job_status | comment | gmt_create | gmt_modify | config | order_id | publish_group_id | publish_number | is_transaction | last_execute_time | finished_time | creator_name | creator_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | -2 |  | 2025-06-30 10:12:26 | 2025-06-30 10:37:38 | {"ghost":{}} | 20638 | 1402 | 1 | 0 | 0000-00-00 00:00:00 | 0000-00-00 00:00:00 | 彭东稳 | 10006019 |
| 5 | -2 |  | 2025-06-30 10:41:24 | 2025-06-30 11:12:48 | {"ghost":{}} | 20639 | 1403 | 1 | 0 | 0000-00-00 00:00:00 | 0000-00-00 00:00:00 | 彭东稳 | 10006019 |
| 6 | -2 |  | 2025-06-30 11:13:17 | 2025-06-30 11:30:00 | {"ghost":{}} | 20640 | 1404 | 1 | 0 | 0000-00-00 00:00:00 | 0000-00-00 00:00:00 | 彭东稳 | 10006019 |

---

## db_act_data_archive_group_task (约 16 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| db_act_data_archive_group_id | bigint | NO | MUL | 0 |  |
| order_id | bigint | NO |  | 0 |  |
| task_group_id | bigint | NO |  | 0 |  |
| mainbody | varchar(200) | NO |  |  |  |
| region_id | varchar(200) | NO |  |  |  |
| db_instance_id | varchar(200) | NO |  |  |  |
| schema_id | bigint | NO |  | 0 |  |
| schema_name | varchar(200) | NO |  |  |  |
| search_name | varchar(200) | NO |  |  |  |
| instance_type | varchar(200) | NO |  |  |  |
| instance_host | varchar(200) | NO |  |  |  |
| instance_port | int | NO |  | 3306 |  |
| logic | tinyint(1) | NO |  | 0 |  |
| job_status | int | NO |  | 0 |  |
| finished_time | timestamp | YES |  | NULL |  |
| plan_exec_time | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| gmt_create | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| gmt_modify | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| chunk_size | bigint | NO |  | 2000 |  |
| is_transaction | tinyint(1) | NO |  | 0 |  |
| optimize_row_scan | tinyint(1) | NO |  | 0 |  |
| last_execute_time | timestamp | NO |  | 0000-00-00 00:00:00 |  |
| comment | longtext | YES |  | NULL |  |
| dispatch_comment | longtext | YES |  | NULL |  |
| target_instance_id | varchar(200) | NO |  |  |  |
| target_instance_type | varchar(200) | NO |  |  |  |
| target_instance_host | varchar(200) | NO |  |  |  |
| target_instance_port | int | NO |  | 3306 |  |
| target_schema_id | bigint | NO |  | 0 |  |
| target_schema_name | varchar(200) | NO |  |  |  |

**样例数据:**

| id | search_name | instance_type | instance_host | instance_port | logic | job_status | finished_time | plan_exec_time | gmt_create | gmt_modify | db_act_data_archive_group_id | chunk_size | is_transaction | optimize_row_scan | last_execute_time | comment | dispatch_comment | target_instance_id | target_instance_type | target_instance_host | target_instance_port | order_id | target_schema_id | target_schema_name | task_group_id | mainbody | region_id | db_instance_id | schema_id | schema_name |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | dw_onedba@rm-uf6e7tt4w809o579j.mysql.rds.aliyuncs.com:3306 [ | acs_rds | rm-uf6e7tt4w809o579j.mysql.rds.aliyuncs.com | 3306 | 0 | 0 | 0000-00-00 00:00:00 | 2025-06-30 10:12:26 | 2025-06-30 10:12:26 | 2025-06-30 10:12:26 | 4 | 0 | 0 | 0 | 0000-00-00 00:00:00 |  |  | rm-uf6e7tt4w809o579j | acs_rds | rm-uf6e7tt4w809o579j.mysql.rds.aliyuncs.com | 3306 | 20638 | 69737512 | dw_onedba | 1900 | shizhuang | cn-shanghai | rm-uf6e7tt4w809o579j | 69737512 | dw_onedba |
| 2 | dw_onedba@rm-uf6e7tt4w809o579j.mysql.rds.aliyuncs.com:3306 [ | acs_rds | rm-uf6e7tt4w809o579j.mysql.rds.aliyuncs.com | 3306 | 0 | 0 | 0000-00-00 00:00:00 | 2025-06-30 10:41:25 | 2025-06-30 10:41:24 | 2025-06-30 10:41:24 | 5 | 0 | 0 | 0 | 0000-00-00 00:00:00 |  |  | rm-uf60mcmiq8s8v5dt2 | acs_rds | rm-uf60mcmiq8s8v5dt2.mysql.rds.aliyuncs.com | 3306 | 20639 | 24223598 | dw_onedba_cs | 1902 | shizhuang | cn-shanghai | rm-uf6e7tt4w809o579j | 69737512 | dw_onedba |
| 3 | dw_onedba@rm-uf6e7tt4w809o579j.mysql.rds.aliyuncs.com:3306 [ | acs_rds | rm-uf6e7tt4w809o579j.mysql.rds.aliyuncs.com | 3306 | 0 | 0 | 0000-00-00 00:00:00 | 2025-06-30 11:13:18 | 2025-06-30 11:13:17 | 2025-06-30 11:13:17 | 6 | 0 | 0 | 0 | 0000-00-00 00:00:00 |  |  | rm-uf60mcmiq8s8v5dt2 | acs_rds | rm-uf60mcmiq8s8v5dt2.mysql.rds.aliyuncs.com | 3306 | 20640 | 24223598 | dw_onedba_cs | 1153 | shizhuang | cn-shanghai | rm-uf6e7tt4w809o579j | 69737512 | dw_onedba |

---

## order_audit_record (约 22839 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| order_id | bigint | NO | MUL | 0 |  |
| schema_id | bigint | NO | MUL | 0 |  |
| seq_no | bigint | NO |  | 0 |  |
| stage | varchar(200) | NO |  |  |  |
| stage_status | varchar(200) | YES |  |  |  |
| error_level | int | NO |  | 0 |  |
| error_message | text | YES |  | NULL |  |
| risk_level | int | NO |  | 0 |  |
| risk_message | text | YES |  | NULL |  |
| sql_text | longtext | YES |  | NULL |  |
| sql_type | varchar(200) | NO |  |  |  |
| affected_rows | bigint | NO |  | 0 |  |
| schema_name | varchar(200) | NO |  |  |  |
| table_name | varchar(200) | NO |  |  |  |
| backup_dbname | varchar(2000) | YES |  |  |  |
| execute_time | varchar(100) | YES |  |  |  |
| sqlsha1 | varchar(300) | YES |  |  |  |
| backup_time | varchar(100) | YES |  |  |  |
| target_table_name | varchar(600) | NO |  |  |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | risk_message | sql_text | sql_type | affected_rows | schema_name | table_name | backup_dbname | execute_time | sqlsha1 | backup_time | order_id | target_table_name | create_time | update_time | schema_id | seq_no | stage | stage_status | error_level | error_message | risk_level |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 15 |  | use db |  | 0 |  |  |  | 0 |  | 0 | 13 |  | 2022-04-28 14:11:33 | 2022-04-28 14:11:33 | 63876 | 0 | CHECKED | Audit Completed | 2 | con:0 Error 1045: Access denied for user 'dba_monitor'@'10.2 | 0 |
| 16 |  | use db |  | 0 |  |  |  | 0 |  | 0 | 233 |  | 2022-04-28 17:47:01 | 2022-04-28 17:47:01 | 63879 | 0 | CHECKED | Audit Completed | 2 | con:0 dial tcp: lookup archive-tidb.shizhuang-inc.com: no su | 0 |
| 17 |  | use db |  | 0 |  |  |  | 0 |  | 0 | 234 |  | 2022-04-28 21:24:27 | 2022-04-28 21:24:27 | 63876 | 0 | CHECKED | Audit Completed | 2 | con:0 dial tcp 10.240.89.119:4000: connect: connection refus | 0 |

---

## order_audit_record_result (约 497 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| order_id | bigint | NO | MUL | 0 |  |
| schema_id | bigint | NO |  | 0 |  |
| search_name | varchar(600) | NO |  |  |  |
| status_code | int | NO |  | 0 |  |
| status_desc | varchar(100) | NO |  |  |  |
| affected_rows | bigint | NO |  | 0 |  |
| success_count | bigint | NO |  | 0 |  |
| error_count | bigint | NO |  | 0 |  |
| error_message | varchar(2000) | NO |  |  |  |
| warn_count | bigint | NO |  | 0 |  |
| sql_count | bigint | NO |  | 0 |  |
| target_schema_id | bigint | NO |  | 0 |  |
| target_search_name | varchar(1000) | NO |  |  |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | error_message | warn_count | sql_count | target_schema_id | target_search_name | create_time | update_time | order_id | schema_id | search_name | status_code | status_desc | affected_rows | success_count | error_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 9 |  | 0 | 1 | 0 |  | 2022-04-28 14:11:33 | 2022-04-28 14:11:33 | 13 | 63876 |  | 0 | 未通过 | 0 | 0 | 1 |
| 10 |  | 0 | 1 | 0 |  | 2022-04-28 17:47:01 | 2022-04-28 17:47:01 | 233 | 63879 |  | 0 | 未通过 | 0 | 0 | 1 |
| 11 |  | 0 | 1 | 0 |  | 2022-04-28 21:24:27 | 2022-04-28 21:24:27 | 234 | 63876 |  | 0 | 未通过 | 0 | 0 | 1 |

---

## order_audit_result (约 546 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| order_id | bigint | NO | UNI | 0 |  |
| status_code | int | NO |  | 0 |  |
| status_desc | varchar(100) | NO |  |  |  |
| risk_code | int | NO |  | 0 |  |
| risk_desc | varchar(100) | NO |  |  |  |
| affected_rows | bigint | NO |  | 0 |  |
| success_count | bigint | NO |  | 0 |  |
| error_count | bigint | NO |  | 0 |  |
| error_message | varchar(2000) | NO |  |  |  |
| warn_count | bigint | NO |  | 0 |  |
| sql_count | bigint | NO |  | 0 |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | error_message | warn_count | sql_count | create_time | update_time | order_id | status_code | status_desc | risk_code | risk_desc | affected_rows | success_count | error_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 9 |  | 0 | 1 | 2022-04-28 14:11:33 | 2022-04-28 14:11:33 | 13 | 0 | 未通过 | 0 |  | 0 | 0 | 1 |
| 10 |  | 0 | 1 | 2022-04-28 17:47:01 | 2022-04-28 17:47:01 | 233 | 0 | 未通过 | 0 |  | 0 | 0 | 1 |
| 11 |  | 0 | 1 | 2022-04-28 21:24:27 | 2022-04-28 21:24:27 | 234 | 0 | 未通过 | 0 |  | 0 | 0 | 1 |

---

## itinerant_ali_rds_backup (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| itinerant_date | date | NO |  | NULL |  |
| db_instance_id | varchar(50) | NO | MUL | NULL |  |
| description | varchar(50) | NO |  |  |  |
| backup_id | bigint | NO |  | 0 |  |
| backup_mode | varchar(50) | NO |  |  |  |
| encryption | varchar(500) | NO |  |  |  |
| backup_db_names | text | YES |  | NULL |  |
| checksum | varchar(32) | NO |  |  |  |
| backup_type | varchar(50) | NO |  |  |  |
| engine | varchar(50) | NO |  |  |  |
| backup_method | varchar(50) | NO |  |  |  |
| engine_version | varchar(50) | NO |  |  |  |
| backup_initiator | varchar(50) | NO |  |  |  |
| backup_intranet_download_url | text | YES |  | NULL |  |
| storage_class | varchar(20) | NO |  |  |  |
| backup_size | bigint | NO |  | 0 |  |
| is_avail | tinyint | NO |  | 0 |  |
| slave_status | text | YES |  | NULL |  |
| host_instance_id | bigint | NO |  | 0 |  |
| store_status | varchar(20) | NO |  |  |  |
| backup_download_url | text | YES |  | NULL |  |
| backup_start_time | datetime | NO |  | NULL |  |
| backup_end_time | datetime | NO |  | NULL |  |
| consistent_time | datetime | NO |  | NULL |  |
| meta_status | varchar(20) | NO |  |  |  |
| backup_scale | varchar(20) | NO |  |  |  |
| backup_location | varchar(20) | NO |  |  |  |
| backup_status | varchar(20) | NO |  |  |  |
| created_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| updated_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

---

## itinerant_ali_rds_binlog_backup (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| itinerant_date | date | NO | PRI | NULL |  |
| db_instance_id | varchar(50) | NO | MUL | NULL |  |
| description | varchar(50) | NO |  |  |  |
| host_instance_id | bigint | NO |  | NULL |  |
| download_link | text | YES |  | NULL |  |
| intranet_download_link | text | YES |  | NULL |  |
| checksum | varchar(32) | NO |  |  |  |
| remote_status | varchar(32) | NO |  |  |  |
| log_file_name | varchar(100) | NO |  |  |  |
| file_size | bigint | NO |  | 0 |  |
| log_begin_time | datetime | NO |  | NULL |  |
| log_end_time | datetime | NO |  | NULL |  |
| link_expired_time | datetime | YES |  | NULL |  |
| created_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| updated_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

---

## itinerant_api_auth (约 1 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| name | varchar(64) | NO | UNI |  |  |
| auth_key | varchar(32) | NO | UNI |  |  |
| created_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| updated_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | name | auth_key | created_time | updated_time |
| --- | --- | --- | --- | --- |
| 1 | dba | 151EC3595EA388C23E59366329FAB709 | 2025-06-13 16:53:57 | 2025-06-13 16:53:57 |

---

## slow_log_aggregation (约 7296074 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| finger | varchar(256) | NO | MUL | NULL |  |
| execution_time | bigint | NO |  | 0 |  |
| amount | int | NO |  | 1 |  |
| create_time | bigint | NO |  | 0 |  |
| modify_time | bigint | NO |  | 0 |  |

**样例数据:**

| id | finger | execution_time | amount | create_time | modify_time |
| --- | --- | --- | --- | --- | --- |
| 1 | 560156b0132cb054abdf5e0b0a6ad354a4935845d387b853ff8fcd6bf1df | 1651312919 | 1 | 1651313219 | 1651313219 |
| 2 | 8cc7ad5b9dab827a84546421ca606f56e742dd1ae178db34d912235114f0 | 1651312919 | 1 | 1651313219 | 1651313219 |
| 3 | 560156b0132cb054abdf5e0b0a6ad354a4935845d387b853ff8fcd6bf1df | 1651312906 | 1 | 1651313220 | 1651313220 |

---

## slow_log_assign (约 2 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| slow_log_id | bigint | NO | UNI | 0 |  |
| assignor_user_id | varchar(255) | NO |  |  |  |
| assignor_username | varchar(255) | NO |  |  |  |
| risk_level | varchar(255) | NO |  |  |  |
| status_code | varchar(255) | NO |  |  |  |
| status_desc | varchar(255) | NO |  |  |  |
| handler_user_id | varchar(255) | NO |  |  |  |
| handler_username | varchar(255) | NO |  |  |  |
| confirm_time | datetime | NO |  | 0000-00-00 00:00:00 |  |
| handle_time | datetime | NO |  | 0000-00-00 00:00:00 |  |
| complete_time | datetime | NO |  | 0000-00-00 00:00:00 |  |
| is_finished | int | NO |  | 0 |  |
| assignor_comment | varchar(2000) | NO |  |  |  |
| handler_comment | varchar(2000) | NO |  |  |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | confirm_time | handle_time | complete_time | is_finished | assignor_comment | handler_comment | create_time | update_time | slow_log_id | assignor_user_id | assignor_username | risk_level | status_code | status_desc | handler_user_id | handler_username |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | 0000-00-00 00:00:00 | 0000-00-00 00:00:00 | 0000-00-00 00:00:00 | 0 | xxxx |  | 2022-06-08 22:50:15 | 2022-06-08 22:50:15 | 6541 | 10006019 | 彭东稳 | 正常 | waitingConfirm | 待认领 | 10006019 | 彭东稳 |
| 3 | 0000-00-00 00:00:00 | 0000-00-00 00:00:00 | 0000-00-00 00:00:00 | 0 | xxxxxx |  | 2022-06-08 22:50:31 | 2022-06-08 22:50:31 | 6542 | 10006019 | 彭东稳 | 正常 | waitingConfirm | 待认领 | 10006019 | 彭东稳 |

---

## slow_log_config (约 10 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | int | NO | PRI | NULL | auto_increment |
| webhook | int | NO | MUL | 0 |  |
| instance_id | varchar(64) | NO |  |  |  |
| instance_name | varchar(600) | NO |  |  |  |
| schema_name | varchar(64) | NO |  |  |  |
| is_delete | tinyint | NO |  | 0 |  |

**样例数据:**

| id | webhook | instance_id | instance_name | schema_name | is_delete |
| --- | --- | --- | --- | --- | --- |
| 1 | 1 | rm-bp1s695vurg294618 |  | du_trade_oversea_cross_border_db | 0 |
| 2 | 1 | rm-bp108866006lb2yat |  | du_trade_oversea_cbc_db | 0 |
| 3 | 1 | rm-bp10w319wcz1b7y52 |  | dw_cdeposit | 0 |

---

## codis_assembly_admin (约 10 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| assembly_name | varchar(128) | NO | MUL | NULL |  |
| assembly_type | varchar(64) | NO |  | NULL |  |
| assembly_version | varchar(64) | NO |  | NULL |  |
| is_delete | tinyint | NO |  | 0 |  |
| create_time | bigint | NO |  | 0 |  |
| modify_time | bigint | NO |  | 0 |  |

**样例数据:**

| id | assembly_name | assembly_type | assembly_version | is_delete | create_time | modify_time |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | codis-proxy | proxy |  | 1 | 0 | 0 |
| 2 | codis-server | server |  | 1 | 0 | 0 |
| 4 | codis-proxy | proxy | 1.3.0 | 1 | 0 | 0 |

---

## codis_bigkey_parser_task (约 59 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| instance_id | varchar(128) | NO | MUL | NULL |  |
| task_id | bigint | NO |  | NULL |  |
| task_state | tinyint | NO |  | 0 |  |
| nodes_total | int | NO |  | 0 |  |
| nodes_return | int | NO |  | 0 |  |
| err_msg | varchar(512) | NO |  |  |  |
| create_time | bigint | NO |  | 0 |  |
| modify_time | bigint | NO |  | 0 |  |
| node_id | varchar(64) | NO |  |  |  |
| task_type | int | NO |  | 0 |  |

**样例数据:**

| id | node_id | task_type | instance_id | task_id | task_state | nodes_total | nodes_return | err_msg | create_time | modify_time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 |  | 0 | kv-redis-test-1 | 1667998436887031 | 1 | 1 | 1 |  | 1667998436 | 1667998447 |
| 2 |  | 0 | kv-redis-test-1 | 1667998603060854 | 1 | 1 | 1 |  | 1667998603 | 1667998613 |
| 3 |  | 0 | kv-redis-test-1 | 1668051090946570 | 1 | 1 | 1 |  | 1668051090 | 1668051102 |

---

## codis_bigkey_prefix_count (约 9087 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| instance_id | varchar(128) | NO | MUL | NULL |  |
| node_id | varchar(128) | NO | MUL |  |  |
| task_id | bigint | NO |  | NULL |  |
| key_prefix | varchar(512) | NO |  |  |  |
| key_type | varchar(64) | NO |  |  |  |
| key_bytes | bigint | NO |  | 0 |  |
| key_amount | bigint | NO |  | 0 |  |
| create_time | bigint | NO |  | 0 |  |
| modify_time | bigint | NO |  | 0 |  |

**样例数据:**

| id | modify_time | instance_id | node_id | task_id | key_prefix | key_type | key_bytes | key_amount | create_time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1667998447 | kv-redis-test-1 | 127.0.0.1:6379 | 1667998436887031 | push | string | 123953444 | 688851 | 1667998447 |
| 2 | 1667998447 | kv-redis-test-1 | 127.0.0.1:6379 | 1667998436887031 | push:node | string | 123118604 | 681121 | 1667998447 |
| 3 | 1667998447 | kv-redis-test-1 | 127.0.0.1:6379 | 1667998436887031 | push:node:time | string | 61866768 | 335234 | 1667998447 |

---

## account (约 59248 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| user_type | int | NO |  | 0 |  |
| password | varchar(200) | NO |  |  |  |
| department_id | varchar(200) | YES |  | NULL |  |
| department_name | varchar(200) | YES |  | NULL |  |
| workplace | varchar(200) | NO |  |  |  |
| job_id | varchar(200) | YES |  | NULL |  |
| username | varchar(200) | NO | MUL |  |  |
| nickname | varchar(200) | NO |  |  |  |
| realname | varchar(200) | NO |  |  |  |
| feishu_name | varchar(200) | NO |  |  |  |
| email | varchar(200) | YES |  | NULL |  |
| phone | varchar(200) | YES |  | NULL |  |
| role | int | NO |  | 0 |  |
| role_groups | varchar(200) | NO |  |  |  |
| comment | varchar(200) | YES |  | NULL |  |
| feishu_open_id | varchar(200) | YES | MUL | NULL |  |
| feishu_user_id | varchar(200) | YES | UNI | NULL |  |
| aliyun_user_id | varchar(200) | YES | MUL | NULL |  |
| aliyun_username | varchar(200) | YES | MUL | NULL |  |
| aliyun_dms_user_id | varchar(200) | YES | MUL | NULL |  |
| avatar | varchar(1200) | NO |  |  |  |
| is_active | int | NO |  | 0 |  |
| is_delete | int | NO |  | 0 |  |
| is_allow_login | int | NO |  | 0 |  |
| last_login | datetime | YES |  | NULL |  |
| join_time | varchar(200) | NO |  |  |  |
| manage_leader | varchar(400) | NO |  |  |  |
| professional_leader | varchar(400) | NO |  |  |  |
| bu | int | NO |  | 0 |  |
| token | varchar(1000) | NO |  |  |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | realname | feishu_name | email | phone | role | role_groups | comment | feishu_open_id | feishu_user_id | aliyun_user_id | user_type | aliyun_username | aliyun_dms_user_id | avatar | is_active | is_delete | is_allow_login | last_login | join_time | manage_leader | professional_leader | password | bu | token | create_time | update_time | department_id | department_name | workplace | job_id | username | nickname |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 袁媛 | Jesica(袁媛)-已离职 | yuanyuan0510@shizhuang-inc.com | 15171485020 | 0 |  | NULL | ou_824e572d1e601f31767b7085e2908fe7 | 10008059 | NULL | 5 | yuanyuan0510 | NULL | https://s1-imfile.feishucdn.com/static-resource/v1/v2_ce5079 | 0 | 0 | 0 | NULL | 2021-05-10T00:00:00+08:00 |  |  |  | 1 |  | 2021-05-11 20:56:12 | 2025-07-02 20:00:47 | 2478 | 姚涛组 | 武汉W2 | 210513302 | yuanyuan0510 |  |
| 2 | 静(Jing) | 静(Jing) | wangjing@dewu.com | 18616244113 | 0 |  | NULL | ou_d681aca5ced18f5fee6633c03c4cd645 | 5249 | NULL | 5 | wangjing | NULL | https://s1-imfile.feishucdn.com/static-resource/v1/01598663- | 1 | 0 | 0 | NULL | 2020-03-06T00:00:00+08:00 |  |  |  | 1 |  | 2021-05-11 20:56:12 | 2025-07-02 20:00:12 | 62 | 总裁办 | 互联宝地T7 | 10000107 | wangjing |  |
| 3 | 魏兰 | 篮子(魏兰)-已离职 | weilan@shizhuang-inc.com | 18616261287 | 0 |  | NULL | ou_a9d0788cc19db1a09eb3c4bd57306cd1 | 10002221 | NULL | 5 | weilan | NULL | https://s1-imfile.feishucdn.com/static-resource/v1/v3_00a3_7 | 0 | 0 | 0 | NULL | 2020-09-21T00:00:00+08:00 |  |  |  | 1 |  | 2021-05-11 20:56:12 | 2025-07-02 20:00:22 | 4498 | 供应链综合项目BP | 互联宝地T7 | 200901537 | weilan |  |

---

## account_department_manager (约 6 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| name | varchar(128) | NO |  |  |  |
| code | varchar(128) | YES | UNI |  |  |
| manager_id | varchar(24) | YES |  | NULL |  |
| manager_name | varchar(24) | YES |  | NULL |  |
| enable_leader | int | NO |  | 0 |  |
| enable_manager | int | NO |  | 0 |  |
| create_time | datetime(6) | YES |  | NULL |  |
| update_time | datetime(6) | NO |  | NULL |  |
| is_active | tinyint(1) | YES |  | 1 |  |

**样例数据:**

| id | is_active | name | code | manager_id | manager_name | enable_leader | enable_manager | create_time | update_time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | 1 | 客服技术 | 1257 | 10008423 | 朱学浩 | 0 | 0 | 2024-01-13 15:55:54.000000 | 2024-01-13 15:55:54.000000 |
| 6 | 1 | 无线十组 社区后端 | 1384 | 2414 | 小夏 | 1 | 1 | 2024-01-13 16:04:54.000000 | 2024-01-13 16:04:54.000000 |
| 7 | 1 | 洗护技术 | 2388 | 3178 | 阿志(AZ) | 1 | 1 | 2024-01-13 16:04:54.000000 | 2024-01-13 16:04:54.000000 |

---

## account_open_api_token (约 17 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| user_id | varchar(100) | NO |  |  |  |
| username | varchar(100) | NO |  |  |  |
| token_user | varchar(200) | NO | UNI |  |  |
| token_real | varchar(200) | NO |  |  |  |
| token_value | varchar(600) | NO |  |  |  |
| open_api_list | longtext | YES |  | NULL |  |
| is_api_auth | int | NO |  | 0 |  |
| is_active | int | NO |  | 0 |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | create_time | update_time | user_id | username | token_user | token_real | token_value | open_api_list | is_api_auth | is_active |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2023-05-08 18:50:42 | 2024-09-20 15:47:43 |  |  | onedba | OneDBA | eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VybmFtZSI6Im9uZWR | /api/external/v1/order/detail | 1 | 1 |
| 2 | 2023-05-08 19:54:20 | 2023-05-08 19:54:20 | 10004512 | 黄兴 | onedba_748b3edf-54e2-445e-a84d-dcb3954c1f5f |  | eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VybmFtZSI6Im9uZWR | NULL | 0 | 1 |
| 3 | 2023-05-08 18:50:42 | 2023-05-09 15:29:56 |  |  | pengdongwen |  | eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VybmFtZSI6InBlbmd | NULL | 0 | 1 |

---

## cmdb_application (约 8227 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| code | varchar(100) | NO | MUL |  |  |
| app_id | bigint | NO | MUL | 0 |  |
| name | varchar(45) | NO | MUL |  |  |
| department_id | bigint | NO | MUL | 0 |  |
| department_name | varchar(45) | NO |  |  |  |
| functional_id | varchar(300) | NO |  |  |  |
| functional_name | varchar(45) | NO |  |  |  |
| owner_users | varchar(1000) | NO |  |  |  |
| is_deleted | tinyint(1) | NO |  | 0 |  |
| comment | text | YES |  | NULL |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| owner_user_name | varchar(64) | NO |  |  |  |
| owner_user_real_name | varchar(64) | NO |  |  |  |
| owner_user_id | varchar(64) | NO |  |  |  |
| level | int | NO |  | -1 |  |
| bsd_id | int | NO |  | 0 |  |
| bsd_name | varchar(64) | NO |  |  |  |
| ignore_sras | tinyint | NO | MUL | 0 |  |

**样例数据:**

| id | is_deleted | comment | create_time | update_time | owner_user_name | owner_user_real_name | owner_user_id | level | bsd_id | bsd_name | code | ignore_sras | app_id | name | department_id | department_name | functional_id | functional_name | owner_users |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 20338234 | 0 | NULL | 2023-09-05 22:00:00 | 2025-07-03 10:00:00 | chenronghui | 荣辉(ronghui) | 10008234 | 1 | 70 | 风控 | 100001 | 0 | 100001 | duapp-risk-ng-config-h5 | 94 | 中台风控(含云盾，与操作风险) | 70 | 风控 |  |
| 20338235 | 0 | NULL | 2023-09-05 22:00:00 | 2025-07-03 10:00:00 | zhanghongxiao | 宏霄(Hong) | 10009715 | 2 | 13 | 容器化组 | 100002 | 0 | 100002 | k8s_repository | 39 | 容器技术 | 13 | 容器化组 |  |
| 20338236 | 0 | NULL | 2023-09-05 22:00:00 | 2025-07-03 10:00:00 | xuming | 伊森(Ethan) | 10001171 | 3 | 48 | 客户端架构 | 100004 | 0 | 100004 | duapp-wireless-service | 48 | 无线平台 | 48 | 客户端架构 |  |

---

## cmdb_application_business_domain (约 263 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | int | NO | PRI | NULL | auto_increment |
| functional_id | int | NO | MUL | NULL |  |
| functional_name | varchar(64) | NO |  | NULL |  |
| department_id | int | NO |  | NULL |  |
| department_name | varchar(64) | NO |  | NULL |  |
| create_time | datetime | NO |  | NULL |  |
| modify_time | datetime | NO |  | NULL |  |

**样例数据:**

| id | functional_id | functional_name | department_id | department_name | create_time | modify_time |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 14 | SRE | 3721 | 网络保障三组 | 2024-03-19 18:43:57 | 2024-03-19 18:43:57 |
| 2 | 70 | 风控 | 3592 | 研发二组 | 2024-03-19 18:43:57 | 2024-03-19 18:43:57 |
| 3 | 13 | 容器化组 | 327 | 容器技术 | 2024-03-19 18:43:57 | 2024-03-19 18:43:57 |

---

## cmdb_application_ecs (约 4038 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| app_name | varchar(100) | NO | MUL |  |  |
| main_body | varchar(100) | NO |  |  |  |
| env_type | varchar(100) | NO |  |  |  |
| ecs_id | varchar(300) | NO |  |  |  |
| ecs_ip | varchar(300) | NO |  |  |  |
| region_id | varchar(100) | NO |  |  |  |
| zone_id | varchar(100) | NO |  |  |  |
| cpu | bigint | NO |  | 0 |  |
| memory | bigint | NO |  | 0 |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | memory | create_time | update_time | app_name | main_body | env_type | ecs_id | ecs_ip | region_id | zone_id | cpu |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11057 | 65536 | 2025-07-03 06:00:09 | 2025-07-03 06:00:09 | starrocks | shizhuang | 生产环境 | i-bp17hg5dtyb4gwp24rl2 | 10.252.126.198 | cn-hangzhou | cn-hangzhou-i | 16 |
| 11058 | 65536 | 2025-07-03 06:00:09 | 2025-07-03 06:00:09 | starrocks | shizhuang | 生产环境 | i-bp17hg5dtyb4gwp24rl3 | 10.252.126.197 | cn-hangzhou | cn-hangzhou-i | 16 |
| 11059 | 65536 | 2025-07-03 06:00:09 | 2025-07-03 06:00:09 | starrocks | shizhuang | 生产环境 | i-bp17hg5dtyb4gwp24rl4 | 10.252.126.199 | cn-hangzhou | cn-hangzhou-i | 16 |

---

## grade_sql_advices (约 8360 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| project_id | int | YES | MUL | NULL |  |
| sql_finger | varchar(128) | YES |  | NULL |  |
| advice | varchar(5000) | YES |  | NULL |  |
| create_time | bigint | NO |  | 0 |  |
| modify_time | bigint | NO |  | 0 |  |
| modity_time | bigint | NO |  | 0 |  |

**样例数据:**

| id | project_id | sql_finger | advice | create_time | modify_time | modity_time |
| --- | --- | --- | --- | --- | --- | --- |
| 735 | 11740 | A8D47538F00A1199 | {"Item":"FUN.001","Severity":"L2","Summary":"避免在 WHERE 条件中使用 | 1645537017 | 1645537017 | 0 |
| 736 | 11740 | A8D47538F00A1199 | {"Item":"RES.002","Severity":"L4","Summary":"未使用 ORDER BY 的  | 1645537017 | 1645537017 | 0 |
| 742 | 11740 | 9AFC35B41EBE4107 | {"Item":"STA.001","Severity":"L0","Summary":"'!=' 运算符是非标准的", | 1645537017 | 1645537017 | 0 |

---

## grade_sql_history (约 93968 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| project_id | int | YES | MUL | NULL |  |
| sql_finger | varchar(128) | YES |  | NULL |  |
| sql_finger_print | varchar(3000) | YES |  | NULL |  |
| score | tinyint | YES |  | NULL |  |
| sql | varchar(2000) | YES |  | NULL |  |
| sql_explain | varchar(5000) | YES |  | NULL |  |
| tables | varchar(1000) | YES |  | NULL |  |
| create_time | bigint | NO | MUL | 0 |  |
| modify_time | bigint | NO |  | 0 |  |
| commit_id | varchar(128) | NO | MUL |  |  |
| db | varchar(128) | NO |  |  |  |
| connection_string | varchar(512) | NO |  |  |  |
| attention_rules | text | YES |  | NULL |  |
| sql_string | text | YES |  | NULL |  |
| review_stat | tinyint | NO | MUL | 0 |  |
| review_remark | varchar(512) | NO |  |  |  |
| sql_id | varchar(128) | NO |  |  |  |

**样例数据:**

| id | modify_time | commit_id | db | connection_string | attention_rules | sql_string | review_stat | review_remark | sql_id | project_id | sql_finger | sql_finger_print | score | sql | sql_explain | tables | create_time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 191 | 1645537039 |  |  |  | NULL | NULL | 1 |  |  | 12874 | 47E579CD2B9A35E5 | select id, main_source_id, source_type, add_spu_id, is_del,  | 90 | select id, main_source_id, source_type, add_spu_id, is_del,  | [{"Case":"### Explain信息解读\n\n#### SelectType信息解读\n\n* **SIMP | ["`du_trade_commodity_db`.`commodity_addition_spu_relation`" | 1645537039 |
| 193 | 1645537039 |  |  |  | NULL | NULL | 1 |  |  | 12874 | D1A63193924415B5 | select id, `name`, logo_url, is_show, is_show_story, is_show | 90 | select id, `name`, logo_url, is_show, is_show_story, is_show | [{"Case":"### Explain信息解读\n\n#### SelectType信息解读\n\n* **SIMP | ["`du_trade_commodity_db`.`commodity_brand`"] | 1645537039 |
| 194 | 1645537039 |  |  |  | NULL | NULL | 1 |  |  | 12874 | 7E198E0DE2BA27CC | select id, `name`, logo_url, is_show, is_show_story, is_show | 90 | select id, `name`, logo_url, is_show, is_show_story, is_show | [{"Case":"### Explain信息解读\n\n#### SelectType信息解读\n\n* **SIMP | ["`du_trade_commodity_db`.`commodity_brand`"] | 1645537039 |

---

## grade_sql_history_20220509 (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| project_id | int | YES |  | NULL |  |
| sql_finger | varchar(128) | YES |  | NULL |  |
| sql_finger_print | varchar(3000) | YES |  | NULL |  |
| score | tinyint | YES |  | NULL |  |
| sql | varchar(2000) | YES |  | NULL |  |
| sql_explain | varchar(5000) | YES |  | NULL |  |
| tables | varchar(1000) | YES |  | NULL |  |
| create_time | bigint | NO |  | 0 |  |
| modify_time | bigint | NO |  | 0 |  |
| commit_id | varchar(128) | NO |  |  |  |
| db | varchar(128) | NO |  |  |  |
| connection_string | varchar(512) | NO |  |  |  |
| attention_rules | text | YES |  | NULL |  |
| sql_string | text | YES |  | NULL |  |
| review_stat | tinyint | NO |  | 0 |  |
| review_remark | varchar(512) | NO |  |  |  |

---

## starrocks_cluster (约 121 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| gmt_create | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| gmt_modify | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| cluster_id | varchar(200) | NO | UNI |  |  |
| connection_string | varchar(200) | NO |  |  |  |
| port | int | NO |  | 9030 |  |
| connection_type | tinyint | NO |  | 1 |  |
| engine_version | varchar(200) | NO |  |  |  |
| mainbody | varchar(200) | NO |  |  |  |
| source | varchar(200) | NO |  | aliyun |  |
| region_id | varchar(200) | NO |  |  |  |
| env_type | varchar(20) | NO |  |  |  |
| level | varchar(20) | NO |  |  |  |
| architecture_type | varchar(200) | NO |  |  |  |
| applicant | varchar(1000) | NO |  |  |  |
| app_owner | varchar(255) | NO |  |  |  |
| business_domain_code | varchar(200) | NO |  |  |  |
| applicant_dept_id | varchar(200) | NO |  |  |  |
| app_owner_dept_id | varchar(200) | NO |  |  |  |
| is_release | tinyint | NO |  | 0 |  |
| release_time | timestamp | NO |  | 0000-00-00 00:00:00 |  |

**样例数据:**

| id | source | region_id | env_type | level | architecture_type | applicant | app_owner | business_domain_code | applicant_dept_id | app_owner_dept_id | gmt_create | is_release | release_time | gmt_modify | cluster_id | connection_string | port | connection_type | engine_version | mainbody |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | aliyun | cn-hangzhou | prd | P1 | 存算一体 | 10013630 | 10013630 | 6 |  |  | 2021-11-25 17:36:06 | 1 | 0000-00-00 00:00:00 | 2022-10-08 17:58:55 | sr-obs | 10.240.56.7 | 9030 | 1 | 2.1.14-DEWU-3-d92338a | shizhuang |
| 2 | aliyun | cn-hangzhou | prd | P0 | 存算一体 | 10016796 | 10006966 | 45 |  |  | 2021-11-25 17:36:06 | 1 | 0000-00-00 00:00:00 | 2023-02-08 14:25:50 | sr-delivery_report | 10.240.56.249 | 9030 | 1 | 2.2.10-b101696 | shizhuang |
| 3 | aliyun | cn-hangzhou | prd | P3 | 存算一体 | 10011431,10010633 | 10011431 | 51 |  |  | 2022-04-06 22:27:13 | 1 | 2025-04-01 14:06:58 | 2022-09-20 18:24:02 | sr-algo | 10.226.14.148 | 9030 | 1 |  | shizhuang |

---

## starrocks_cluster_department_cost_rule (约 90 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| gmt_create | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| gmt_modify | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| cluster_id | varchar(200) | NO | MUL |  |  |
| department_id | bigint | NO |  | 0 |  |
| cost_ratio | decimal(5,2) | NO |  | 100.00 |  |
| is_release | tinyint | NO |  | 0 |  |
| release_time | timestamp | NO |  | 0000-00-00 00:00:00 |  |

**样例数据:**

| id | gmt_create | gmt_modify | cluster_id | department_id | cost_ratio | is_release | release_time |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-01-04 00:19:07 | 2026-01-04 00:19:07 | sr-dw_monitor | 1876 | 100.00 | 0 | 0000-00-00 00:00:00 |
| 2 | 2026-01-04 00:19:07 | 2026-01-04 00:19:07 | sr-ee | 3439 | 100.00 | 0 | 0000-00-00 00:00:00 |
| 3 | 2026-01-04 00:19:07 | 2026-01-04 00:19:07 | sr-hw_ee_starrocks | 846 | 100.00 | 0 | 0000-00-00 00:00:00 |

---

## starrocks_cost_checkout (约 96 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| create_time | datetime(3) | NO |  | CURRENT_TIMESTAMP(3) | DEFAULT_GENERATED |
| modify_time | datetime(3) | NO |  | CURRENT_TIMESTAMP(3) | DEFAULT_GENERATED on update CURRENT_TIMESTAMP(3) |
| split_date | date | NO | MUL | NULL |  |
| paas_code | varchar(256) | NO |  | NULL |  |
| department_id | bigint | NO |  | NULL |  |
| instance_id | varchar(256) | NO |  | NULL |  |
| app_id | varchar(256) | NO |  |  |  |
| cluster_id | varchar(256) | NO |  |  |  |
| charge_spec | varchar(256) | NO |  |  |  |
| resource_usage | bigint | NO |  | NULL |  |
| region | varchar(32) | NO |  | 国内 |  |
| algo_scenes | varchar(1000) | YES |  | NULL |  |

**样例数据:**

| id | charge_spec | resource_usage | region | algo_scenes | create_time | modify_time | split_date | paas_code | department_id | instance_id | app_id | cluster_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CPU | 32 | 国内 |  | 2025-09-01 08:19:10.000 | 2025-09-01 08:19:10.000 | 2025-08-30 | StarRocks | 7380 | 10.44.20.1 | starrocks | sr-obs_enhanced |
| 2 | CPU | 32 | 国内 |  | 2025-09-01 08:19:10.000 | 2025-09-01 08:19:10.000 | 2025-08-30 | StarRocks | 7380 | 10.44.20.15 | starrocks | sr-obs_enhanced |
| 3 | CPU | 32 | 国内 |  | 2025-09-01 08:19:10.000 | 2025-09-01 08:19:10.000 | 2025-08-30 | StarRocks | 7380 | 10.44.20.16 | starrocks | sr-obs_enhanced |

---

## workflow_feishu_record (约 336 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| order_id | bigint | NO | MUL | 0 |  |
| workflow_id | bigint | NO |  | 0 |  |
| workflow_task_id | bigint | NO |  | 0 |  |
| content | json | YES |  | NULL |  |
| username | varchar(200) | NO |  |  |  |
| action | varchar(200) | NO |  |  |  |
| is_finished | int | NO |  | 0 |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | update_time | order_id | workflow_id | workflow_task_id | content | username | action | is_finished | create_time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2021-12-12 14:39:43 | 91 | 91 | 240 | {"config": {"wide_screen_mode": true}, "header": {"title": { |  |  | 0 | 2021-12-12 14:39:43 |
| 3 | 2021-12-12 14:49:29 | 92 | 92 | 241 | {"config": {"wide_screen_mode": true}, "header": {"title": { |  |  | 0 | 2021-12-12 14:49:29 |
| 4 | 2021-12-12 14:49:37 | 92 | 92 | 242 | {"config": {"wide_screen_mode": true}, "header": {"title": { |  |  | 0 | 2021-12-12 14:49:37 |

---

## workflow_identify (约 2526 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| instance_id | bigint | NO | MUL | 0 |  |
| task_id | bigint | NO | MUL | 0 |  |
| identify_type | varchar(255) | NO |  |  |  |
| approval_type | varchar(255) | NO |  |  |  |
| user_id | varchar(255) | NO | MUL |  |  |
| username | varchar(255) | NO |  |  |  |
| step | int | NO |  | 0 |  |
| comments | varchar(255) | NO |  |  |  |
| wait_time | bigint | NO |  | 0 |  |
| create_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | wait_time | create_time | update_time | instance_id | task_id | identify_type | approval_type | user_id | username | step | comments |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0 | 2021-11-30 14:37:04 | 2021-11-30 14:37:04 | 1 | 0 | submitter | agreed | 10006019 | 彭东稳 | 0 | 启动流程 |
| 2 | 5 | 2021-11-30 14:37:09 | 2021-11-30 14:37:09 | 1 | 1 | approver | agreed | 10006019 | 彭东稳 | 1 | 同意 |
| 3 | 0 | 2021-11-30 14:37:09 | 2021-11-30 14:37:09 | 1 | 2 | notifier | agreed | 5249 | 王静 | 2 | 抄送节点 |

---

## workflow_instance (约 985 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| order_id | bigint | NO | MUL | 0 |  |
| order_type | varchar(1000) | NO |  |  |  |
| committer_id | bigint | NO |  | 0 |  |
| committer_name | varchar(255) | NO |  |  |  |
| status_code | varchar(255) | NO |  |  |  |
| status_desc | varchar(255) | NO |  |  |  |
| task_id | bigint | NO |  | 0 |  |
| task_count | int | NO |  | 0 |  |
| is_finished | int | NO |  | 0 |  |
| is_filter | int | NO |  | 0 |  |
| create_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | is_finished | is_filter | create_time | update_time | order_id | order_type | committer_id | committer_name | status_code | status_desc | task_id | task_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 0 | 2021-11-30 14:37:04 | 2021-11-30 14:37:13 | 1 | appendWhitelist | 10006019 | 彭东稳 | approved | 审批已通过 | 3 | 3 |
| 2 | 1 | 0 | 2021-11-30 14:41:19 | 2021-11-30 14:41:28 | 2 | createDatabase | 10006019 | 彭东稳 | approved | 审批已通过 | 6 | 3 |
| 3 | 1 | 0 | 2021-11-30 15:14:30 | 2021-11-30 15:14:38 | 3 | createDatabase | 10006019 | 彭东稳 | approved | 审批已通过 | 9 | 3 |

---

## effect_alert_v2 (约 83 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| inspection_date | varchar(32) | NO | UNI | NULL |  |
| year | smallint | NO | MUL | NULL |  |
| month | tinyint | NO |  | NULL |  |
| week | tinyint | NO |  | NULL |  |
| alert_cnt | int | NO |  | 0 |  |
| alert_phone_cnt | int | NO |  | 0 |  |
| event_cnt | int | NO |  | 0 |  |
| event_phone_cnt | int | NO |  | 0 |  |
| order_cnt | int | NO |  | 0 |  |
| created_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| updated_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | order_cnt | created_time | updated_time | inspection_date | year | month | week | alert_cnt | alert_phone_cnt | event_cnt | event_phone_cnt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0 | 2024-07-19 17:08:52 | 2024-07-19 17:08:52 | 2024-05-01 | 2024 | 5 | 18 | 3 | 3 | 5 | 5 |
| 2 | 1 | 2024-07-19 17:08:52 | 2024-07-19 17:08:52 | 2024-05-02 | 2024 | 5 | 18 | 10 | 10 | 14 | 2 |
| 3 | 2 | 2024-07-19 17:08:53 | 2024-07-19 17:08:53 | 2024-05-03 | 2024 | 5 | 18 | 10 | 10 | 204 | 5 |

---

## effect_daily_work_question_v2 (约 14 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| effect_daily_work_id | bigint | NO | MUL | NULL |  |
| question_feishu_id | varchar(50) | NO |  | NULL |  |
| answer_feishu_id | varchar(50) | NO |  |  |  |
| question_content | text | YES |  | NULL |  |
| answer_content | text | YES |  | NULL |  |
| is_solve | tinyint | NO |  | 0 |  |
| created_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| updated_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | effect_daily_work_id | question_feishu_id | answer_feishu_id | question_content | answer_content | is_solve | created_time | updated_time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2 | 10046675 | 10046675 | 愤怒呆呆(陈浩) 对你的日常工作有疑异, 请及进行沟通确认. 日常工作id: 2 | 时间问题 | 1 | 2024-08-08 15:36:04 | 2024-08-09 11:51:25 |
| 2 | 2 | 10046675 | 10046675 | 愤怒呆呆(陈浩) 对你的日常工作有疑异, 请及进行沟通确认. 日常工作id: 2 | 没有问题1 | 1 | 2024-08-08 15:36:09 | 2024-08-09 11:49:25 |
| 3 | 2 | 10046675 | 10046675 | 愤怒呆呆(陈浩) 对你的日常工作有疑异, 请及进行沟通确认. 日常工作id: 2 | 时间问题 | 1 | 2024-08-08 15:36:09 | 2024-08-09 11:51:32 |

---

## effect_daily_work_type_v2 (约 9 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| name | varchar(100) | NO | UNI | NULL |  |
| created_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| updated_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | name | created_time | updated_time |
| --- | --- | --- | --- |
| 1 | 问题咨询 | 2024-08-08 22:00:22 | 2024-08-08 22:00:22 |
| 2 | 问题排查 | 2024-08-08 22:00:22 | 2024-08-08 22:00:22 |
| 3 | SQL优化 | 2024-08-08 22:00:22 | 2024-08-08 22:00:22 |

---

## query_collection (约 19 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| user_id | varchar(100) | NO | MUL |  |  |
| username | varchar(100) | NO |  |  |  |
| title | varchar(100) | NO |  |  |  |
| sql_text | text | YES |  | NULL |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | user_id | username | title | sql_text | create_time | update_time |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | 10015017 | 邵飞 | 111 | 222 | 2023-03-08 13:56:32 | 2023-03-08 13:56:32 |
| 11 | 10006019 | 彭东稳 | dsf | SELECT * FROM `apm_app_instance` LIMIT 20;

SELECT * FROM `a | 2024-11-06 16:55:03 | 2024-11-06 16:55:03 |
| 12 | 10006019 | 东青(dongwen) | 日常运维1 | SELECT biz_no,ori_biz_no,fee_type,pay_way,status,is_del,gmt_ | 2025-07-16 10:15:40 | 2025-07-16 10:15:40 |

---

## query_console (约 26 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| user_id | varchar(100) | NO | MUL |  |  |
| username | varchar(100) | NO |  |  |  |
| schema_id | bigint | NO |  | 0 |  |
| force | int | NO |  | 0 |  |
| content | longtext | YES |  | NULL |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | user_id | username | schema_id | force | content | create_time | update_time |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 10006019 | 彭东稳 | 69737512 | 0 | {"panes":[{"title":"SQLConsole","key":"1","closable":false}, | 2025-03-04 22:35:15 | 2026-06-24 20:44:18 |
| 8 | 10006019 | 彭东稳 | 86142697 | 0 | {"panes":[{"title":"SQLConsole","key":"1","closable":false}] | 2025-03-05 20:35:20 | 2025-03-05 20:35:20 |
| 10 | 10006019 | 彭东稳 | 101804861 | 0 | {"panes":[{"title":"SQLConsole","key":"1","closable":false}] | 2025-04-14 11:47:48 | 2025-04-14 11:47:48 |

---

## query_order_record (约 24 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| order_id | bigint | NO | UNI | 0 |  |
| user_id | varchar(100) | NO | MUL |  |  |
| username | varchar(100) | NO |  |  |  |
| status_code | varchar(255) | NO |  |  |  |
| status_desc | varchar(255) | NO |  |  |  |
| schema_id | bigint | NO | MUL | 0 |  |
| schema_name | varchar(200) | NO |  |  |  |
| search_name | varchar(200) | NO |  |  |  |
| sql_text | text | YES |  | NULL |  |
| affect_row | bigint | NO |  | 0 |  |
| exec_limit | bigint | NO |  | 0 |  |
| exec_count | bigint | NO |  | 0 |  |
| start_time | datetime | NO |  | 0000-00-00 00:00:00 |  |
| expire_time | bigint | NO |  | 0 |  |
| comment | varchar(600) | NO |  |  |  |
| create_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | sql_text | affect_row | exec_limit | exec_count | start_time | expire_time | comment | create_time | update_time | order_id | user_id | username | status_code | status_desc | schema_id | schema_name | search_name |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | SELECT * FROM `db_tables` LIMIT 20; | 0 | 0 | 0 | 0000-00-00 00:00:00 | 24 | xxxxx | 2024-01-18 21:36:06 | 2024-01-19 15:03:46 | 20274 | 10006019 | 彭东稳 | canceled | 审批撤销 | 6 | dw_onedba | dw_onedba@rm-uf634hx581tbo18em.mysql.rds.aliyuncs.com:3306 [ |
| 2 | SELECT * FROM `db_billings` LIMIT 20; | 0 | 0 | 0 | 2024-01-19 14:43:54 | 24 | xxxxx | 2024-01-18 21:43:03 | 2024-01-19 14:43:54 | 20275 | 10006019 | 彭东稳 | approved | 审批通过 | 6 | dw_onedba | dw_onedba@rm-uf634hx581tbo18em.mysql.rds.aliyuncs.com:3306 [ |
| 3 | SELECT * FROM `db_tables` LIMIT 20; | 0 | 0 | 0 | 2024-01-19 13:51:44 | 24 | xxxxx | 2024-01-19 13:51:44 | 2024-01-19 13:51:44 | 20276 | 10006019 | 彭东稳 | waitingApprove | 工单审批中 | 6 | dw_onedba | dw_onedba@rm-uf634hx581tbo18em.mysql.rds.aliyuncs.com:3306 [ |

---

## hbase_cost_checkout (约 128 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| create_time | datetime(3) | NO |  | CURRENT_TIMESTAMP(3) | DEFAULT_GENERATED |
| modify_time | datetime(3) | NO |  | CURRENT_TIMESTAMP(3) | DEFAULT_GENERATED on update CURRENT_TIMESTAMP(3) |
| split_date | date | NO | MUL | NULL |  |
| paas_code | varchar(256) | NO |  | NULL |  |
| department_id | bigint | NO |  | NULL |  |
| instance_id | varchar(256) | NO |  | NULL |  |
| app_id | varchar(256) | NO |  |  |  |
| cluster_id | varchar(256) | NO |  |  |  |
| charge_spec | varchar(256) | NO |  |  |  |
| resource_usage | bigint | NO |  | NULL |  |
| region | varchar(32) | NO |  | 国内 |  |
| algo_scenes | varchar(1000) | YES |  | NULL |  |

**样例数据:**

| id | charge_spec | resource_usage | region | algo_scenes | create_time | modify_time | split_date | paas_code | department_id | instance_id | app_id | cluster_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CPU | 8 | 国内 |  | 2025-09-01 08:45:50.000 | 2025-09-01 08:45:50.000 | 2025-08-30 | HBase | 1857 | 10.252.164.85 | du-hbase-public-ssd-c1 | public-ssd-c1 |
| 2 | CPU | 8 | 国内 |  | 2025-09-01 08:45:50.000 | 2025-09-01 08:45:50.000 | 2025-08-30 | HBase | 1857 | 10.252.164.82 | du-hbase-public-ssd-c1 | public-ssd-c1 |
| 3 | CPU | 8 | 国内 |  | 2025-09-01 08:45:50.000 | 2025-09-01 08:45:50.000 | 2025-08-30 | HBase | 1857 | 10.252.164.175 | du-hbase-public-ssd-c1 | public-ssd-c1 |

---

## hbase_inspection_task (约 4 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint unsigned | NO | PRI | NULL | auto_increment |
| db_instance_id | varchar(200) | NO | MUL |  |  |
| namespace | varchar(200) | NO |  |  |  |
| tables | varchar(200) | NO |  |  |  |
| cron_expr | varchar(50) | NO |  |  |  |
| task_type | varchar(20) | NO |  |  |  |
| is_enable | tinyint(1) | NO |  | 0 |  |
| last_execute_time | datetime | YES |  | NULL |  |
| task_config | json | YES |  | NULL |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| modify_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| is_del | tinyint(1) | NO |  | 0 |  |

**样例数据:**

| id | create_time | modify_time | is_del | db_instance_id | namespace | tables | cron_expr | task_type | is_enable | last_execute_time | task_config |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-05-21 16:50:05 | 2026-06-09 15:06:56 | 0 | dba-test | default |  | 4 * * * * | hotRegion | 0 | 2026-06-09 15:04:00 | NULL |
| 5 | 2026-05-21 16:50:05 | 2026-05-25 20:20:17 | 0 | dba-test | default |  | 0 4 * * * | bigKey | 0 | 2026-05-25 20:19:45 | NULL |
| 6 | 2026-05-25 15:30:26 | 2026-05-25 21:07:39 | 0 | user-ssd-c1 | time_picker |  | 0 4 * * * | hotRegion | 0 | 2026-05-25 21:07:22 | NULL |

---

## hbase_open_api_token (约 1 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| feishu_user_id | varchar(100) | NO |  |  |  |
| username | varchar(100) | NO |  |  |  |
| token_user | varchar(200) | NO | UNI |  |  |
| token_real | varchar(200) | NO |  |  |  |
| token_value | varchar(600) | NO |  |  |  |
| open_api_list | longtext | YES |  | NULL |  |
| instance_list | varchar(200) | YES |  | NULL |  |
| is_api_auth | int | NO |  | 0 |  |
| is_active | int | NO |  | 0 |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | is_active | create_time | update_time | feishu_user_id | username | token_user | token_real | token_value | open_api_list | instance_list | is_api_auth |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 1 | 2026-03-11 18:49:05 | 2026-04-27 11:10:52 | 10058467 | yuanzewen | onedba_e57bb34c | onedba_e57bb34c | eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJvbmVkYmFfZTU | all | all | 0 |

---

## risk_dept_order_deduct_v2 (约 154 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| inspection_date | varchar(32) | NO | MUL | NULL |  |
| department | varchar(45) | NO | MUL |  |  |
| department_code | varchar(40) | NO | MUL |  |  |
| dba_owner | varchar(255) | NO |  |  |  |
| sum_deduct | decimal(11,3) | NO |  | 0.000 |  |
| avg_deduct | decimal(11,3) | NO |  | 0.000 |  |
| cnt | int | NO |  | 0 |  |
| created_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| updated_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| year | smallint | NO |  | 0 |  |
| month | tinyint | NO |  | 0 |  |
| week | tinyint | NO |  | 0 |  |

**样例数据:**

| id | updated_time | year | month | week | inspection_date | department | department_code | dba_owner | sum_deduct | avg_deduct | cnt | created_time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 28 | 2024-08-21 18:13:29 | 2024 | 7 | 29 | 2024-07-16 | 技术保障 | 12 | 10006019 | 20.000 | 20.000 | 1 | 2024-08-13 15:27:45 |
| 29 | 2024-08-21 18:13:29 | 2024 | 7 | 29 | 2024-07-16 | 国际技术 | 2 | 10041750 | 20.000 | 20.000 | 1 | 2024-08-13 15:27:45 |
| 30 | 2024-08-21 18:13:29 | 2024 | 7 | 29 | 2024-07-16 | 中间件平台 | 39 | 10006019 | 150.000 | 18.750 | 8 | 2024-08-13 15:27:45 |

---

## risk_instance_order_deduct_v2 (约 187 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| inspection_date | varchar(32) | NO | MUL | NULL |  |
| instance_id | varchar(200) | NO | MUL |  |  |
| instance_name | varchar(50) | NO |  |  |  |
| resource_type | varchar(30) | NO |  |  |  |
| dba_owner | varchar(255) | NO |  |  |  |
| level | varchar(20) | NO |  |  |  |
| department | varchar(45) | NO |  |  |  |
| business_subdomain | varchar(200) | NO |  |  |  |
| department_code | varchar(40) | NO |  |  |  |
| business_subdomain_code | varchar(40) | NO |  |  |  |
| sum_deduct | decimal(11,3) | NO |  | 0.000 |  |
| avg_deduct | decimal(11,3) | NO |  | 0.000 |  |
| cnt | int | NO |  | 0 |  |
| created_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| updated_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| year | smallint | NO |  | 0 |  |
| month | tinyint | NO |  | 0 |  |
| week | tinyint | NO |  | 0 |  |

**样例数据:**

| id | department_code | business_subdomain_code | sum_deduct | avg_deduct | cnt | created_time | updated_time | year | month | week | inspection_date | instance_id | instance_name | resource_type | dba_owner | level | department | business_subdomain |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 58 | 39 | 39 | 20.000 | 20.000 | 1 | 2024-08-13 15:27:45 | 2024-08-21 18:14:19 | 2024 | 7 | 29 | 2024-07-16 | 35ff594846364e47a50e00c6587eb27bin01 | prd-基础架构-jgs | acs_rds | 10006019 | P2 | 中间件平台 | 中间件平台 |
| 59 | 39 | 39 | 20.000 | 20.000 | 1 | 2024-08-13 15:27:45 | 2024-08-21 18:14:19 | 2024 | 7 | 29 | 2024-07-16 | mysql-6434001d58b8 | prd-基础架构-火山云 | acs_rds | 10006019 | P1 | 中间件平台 | 中间件平台 |
| 60 | 69 | 70 | 20.000 | 20.000 | 1 | 2024-08-13 15:27:45 | 2024-08-21 18:14:19 | 2024 | 7 | 29 | 2024-07-16 | rm-2vc70806xen61g118 | prd-风控-小贷-成都 | acs_rds | 10006019 | P1 | 风控 | 风控-风控技术 |

---

## risk_order_dept_metric_v2 (约 1 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| department | varchar(45) | NO |  |  |  |
| department_code | varchar(40) | NO | UNI |  |  |
| level1_value | decimal(8,3) | NO |  | 0.000 |  |
| level1_factor | decimal(8,3) | NO |  | 0.000 |  |
| level2_value | decimal(8,3) | NO |  | 0.000 |  |
| level2_factor | decimal(8,3) | NO |  | 0.000 |  |
| level3_value | decimal(8,3) | NO |  | 0.000 |  |
| level3_factor | decimal(8,3) | NO |  | 0.000 |  |
| level4_value | decimal(8,3) | NO |  | 0.000 |  |
| level4_factor | decimal(8,3) | NO |  | 0.000 |  |
| created_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| updated_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | level4_value | level4_factor | created_time | updated_time | department | department_code | level1_value | level1_factor | level2_value | level2_factor | level3_value | level3_factor |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 500.000 | 0.010 | 2024-08-23 16:10:13 | 2024-08-23 16:10:13 | default | default | 20.000 | 0.500 | 60.000 | 0.100 | 200.000 | 0.020 |

---

## system_config (约 39 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| name | varchar(255) | NO | UNI |  |  |
| arg_key | varchar(255) | NO | UNI |  |  |
| arg_value | text | NO |  | NULL |  |
| user_id | varchar(255) | NO |  |  |  |
| username | varchar(255) | NO |  |  |  |
| comments | varchar(255) | NO |  |  |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | name | arg_key | arg_value | user_id | username | comments | create_time | update_time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | MongoDB创建库开发环境实例 | mongodb:create:database:dev:instance | dds-uf68c7b06751ec84,dds-uf606abca184fb34 |  |  | MongoDB创建库开发环境实例 | 2021-11-29 20:28:46 | 2021-11-29 20:28:46 |
| 9 | 实例升配成本大于10万审批模板 | config:change:order:large:approval:template | 1033 |  |  | 实例升降配工单审批模板，-1为免审批 | 2021-12-16 17:32:07 | 2021-12-16 17:32:07 |
| 33 | Hbase实例规格 | instance:class:hbase | [{"instanceClass": "hbase.sn1.large", "instanceClassDesc": " |  |  | Hbase实例规格 | 2022-05-09 12:40:33 | 2022-05-09 12:40:33 |

---

## system_password (约 2 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| title | varchar(200) | NO | MUL |  |  |
| username | varchar(200) | NO |  |  |  |
| password | varchar(200) | NO |  |  |  |
| comment | text | YES |  | NULL |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | title | username | password | comment | create_time | update_time |
| --- | --- | --- | --- | --- | --- | --- |
| 8130 | MySQL | xxs | xxx | kkkk | 2024-12-25 18:44:25 | 2024-12-25 21:01:28 |
| 8131 | xxx | ddd | ENC(B1NRey6+yQGY985FcrKgbA==) | dfdjkfdjkf的跨机房就的空间风控的的空间风控搭建点击反馈的尽快搞京东方看点击反馈就 | 2024-12-25 20:54:25 | 2024-12-25 21:08:12 |

---

## system_security_rule (约 15 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| rule_set_name | varchar(200) | NO | UNI |  |  |
| rule_set_type | varchar(200) | NO |  | 0 |  |
| rule_set_value | json | YES |  | NULL |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| comments | text | YES |  | NULL |  |

**样例数据:**

| id | rule_set_name | rule_set_type | rule_set_value | create_time | update_time | comments |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | MySQL安全规则-生产环境 | db_mysql | {"data_change": {"base_config": "base_config", "sql_audit_ru | 2023-08-25 13:19:30 | 2023-08-25 13:19:30 | MySQL安全规则 |
| 2 | TiDB安全规则-生产环境 | db_tidb | {"data_change": {"base_config": "base_config", "sql_audit_ru | 2023-08-28 15:36:19 | 2023-08-28 15:36:19 | TiDB安全规则 |
| 3 | 效率工程-生产环境 | db_mysql | {"data_change": {"base_config": "base_config", "sql_audit_ru | 2023-08-28 15:28:55 | 2023-08-28 15:28:55 | 效率工程专用 |

---

## approval_node (约 15 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| name | varchar(100) | NO | UNI |  |  |
| type | int | NO |  | 0 |  |
| creator | varchar(100) | NO |  |  |  |
| approvers | text | YES |  | NULL |  |
| comments | varchar(100) | NO |  |  |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | name | type | creator | approvers | comments | create_time | update_time |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1000 | Admin | 0 |  |  | 系统节点，动态计算，由管理员来完成审批 | 2021-10-15 15:11:54 | 2021-10-15 15:11:54 |
| 1001 | DBA | 0 |  |  | 系统节点，动态计算，由用户操作的资源对应的DBA来完成审批 | 2021-10-15 15:11:54 | 2021-10-15 15:11:54 |
| 1002 | Owner | 0 |  |  | 系统节点，动态计算，由用户操作的资源对应的Owner来完成审批 | 2021-10-15 15:11:54 | 2021-10-15 15:11:54 |

---

## approval_template (约 23 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| name | varchar(100) | NO | MUL |  |  |
| type | int | NO |  | 0 |  |
| creator | varchar(100) | NO |  |  |  |
| approval_node | text | YES |  | NULL |  |
| comments | varchar(100) | NO |  |  |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | name | type | creator | approval_node | comments | create_time | update_time |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1000 | Admin | 0 |  | 1000 | 系统定义审批线，仅需管理员审批 | 2021-10-15 15:07:11 | 2021-10-15 15:07:11 |
| 1001 | DBA | 0 |  | 1001 | 系统定义审批线，仅需DBA审批 | 2021-10-15 15:07:17 | 2021-10-15 15:07:17 |
| 1002 | Owner | 0 |  | 1002 | 系统定义审批线，仅需Owner审批 | 2021-10-15 15:07:24 | 2021-10-15 15:07:24 |

---

## approval_template_node (约 57 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| template_id | bigint | NO | MUL | 0 |  |
| node_id | bigint | NO |  | 0 |  |
| run_mode | varchar(100) | NO |  |  |  |
| is_forward | int | NO |  | 1 |  |
| is_reminder | int | NO |  | 1 |  |
| approval_mode | varchar(10) | NO |  | and |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | template_id | node_id | run_mode | is_forward | is_reminder | approval_mode | create_time | update_time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1000 | 1000 | approval | 1 | 1 | or | 2021-10-15 15:07:52 | 2021-10-15 15:07:52 |
| 2 | 1001 | 1001 | approval | 1 | 1 | or | 2021-10-15 15:07:52 | 2021-10-15 15:07:52 |
| 3 | 1002 | 1002 | approval | 1 | 1 | or | 2021-10-15 15:07:52 | 2021-10-15 15:07:52 |

---

## datax_task_log (约 6779 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| task_id | bigint | NO |  | 0 |  |
| log_content | varchar(1024) | NO |  |  |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| modify_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| config_file | varchar(512) | NO |  |  |  |
| progress | varchar(256) | NO |  |  |  |

**样例数据:**

| id | task_id | log_content | create_time | modify_time | config_file | progress |
| --- | --- | --- | --- | --- | --- | --- |
| 139 | 6 | DataX (DATAX-OPENSOURCE-3.0), From Alibaba ! | 2022-01-05 19:02:21 | 2022-01-05 19:02:21 |  |  |
| 140 | 6 | Copyright (C) 2010-2017, Alibaba Group. All Rights Reserved. | 2022-01-05 19:02:21 | 2022-01-05 19:02:21 |  |  |
| 141 | 6 | 2022-01-05 19:02:22.104 [main] INFO  VMInfo - VMInfo# operat | 2022-01-05 19:02:22 | 2022-01-05 19:02:22 |  |  |

---

## datax_task_records (约 159 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| task_id | bigint | NO | MUL | 0 |  |
| child_task_name | varchar(256) | NO |  |  |  |
| source_db_name | varchar(256) | NO |  |  |  |
| source_table_name | varchar(256) | NO |  |  |  |
| progress | varchar(512) | NO |  |  |  |
| create_time | bigint | NO |  | 0 |  |
| modify_time | bigint | NO |  | 0 |  |
| log_file_name | varchar(512) | NO |  |  |  |
| status | tinyint | NO |  | 0 |  |
| oss_dir | varchar(512) | NO |  |  |  |

**样例数据:**

| id | status | oss_dir | task_id | child_task_name | source_db_name | source_table_name | progress | create_time | modify_time | log_file_name |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0 |  | 22 | test-migration12022 2141153534973000 | dw_onedba_d1 | approval_template |  | 1644810811 | 1644810811 | /tmp/datax-jobs/test-migration1/dw_onedba_d1/approval_templa |
| 2 | 0 |  | 22 | test-migration12022 2141153534973000 | dw_onedba_d1 | approval_template_node |  | 1644810814 | 1644810814 | /tmp/datax-jobs/test-migration1/dw_onedba_d1/approval_templa |
| 3 | 0 |  | 22 | test-migration12022 214115443668000 | dw_onedba_d1 | approval_template |  | 1644810840 | 1644810840 | /tmp/datax-jobs/test-migration1/dw_onedba_d1/approval_templa |

---

## datax_tasks (约 18 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| task_name | varchar(128) | YES |  | NULL |  |
| config_json | longtext | YES |  | NULL |  |
| file_path | varchar(512) | YES |  | NULL |  |
| is_valid | tinyint | YES |  | NULL |  |
| create_time | bigint | NO |  | 0 |  |
| modity_time | bigint | NO |  | 0 |  |
| last_log | varchar(100) | NO |  |  |  |
| progress | varchar(100) | NO |  |  |  |
| source_type | varchar(32) | NO |  |  |  |
| dest_type | varchar(32) | NO |  |  |  |
| oss_dir | varchar(512) | NO |  |  |  |

**样例数据:**

| id | source_type | dest_type | oss_dir | task_name | config_json | file_path | is_valid | create_time | modity_time | last_log | progress |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 26 |  |  |  | test-migration1 | {"speed":10,"data_sources":null,"tasks":[{"name":"test-migra |  | 0 | 1644824791 | 1644824791 |  |  |
| 27 | MySQL | MySQL |  | 测试 | {"task_id":27,"speed":10,"data_sources":null,"tasks":[{"name |  | 0 | 1650360187 | 1650360187 |  |  |
| 28 |  |  |  | 测试 | {"task_id":0,"speed":10,"data_sources":null,"tasks":[{"name" |  | 1 | 1644918978 | 1644918978 |  |  |

---

## tbl_cluster (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint unsigned | NO | PRI | NULL | auto_increment |
| created_at | datetime(3) | YES |  | NULL |  |
| updated_at | datetime(3) | YES |  | NULL |  |
| deleted_at | datetime(3) | YES | MUL | NULL |  |
| cluster_name | varchar(191) | YES | UNI | NULL |  |
| config | longtext | YES |  | NULL |  |

---

## tbl_query_history (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| cluster | varchar(191) | YES | MUL | NULL |  |
| checksum | varchar(191) | NO | PRI | NULL |  |
| query | longtext | YES |  | NULL |  |
| create_time | datetime(3) | YES |  | NULL |  |

---

## tbl_task (约 3 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| task_id | varchar(191) | NO | PRI | NULL |  |
| status | bigint | YES |  | NULL |  |
| config | longtext | YES |  | NULL |  |

**样例数据:**

| task_id | status | config |
| --- | --- | --- |
| 59056b5f-6ca8-bd6c-4396-d20c89f0f16b | 2 | {"TaskId":"59056b5f-6ca8-bd6c-4396-d20c89f0f16b","ClusterNam |
| ce385283-fa6b-655f-badd-366fbaf0c2db | 2 | {"TaskId":"ce385283-fa6b-655f-badd-366fbaf0c2db","ClusterNam |
| da74b716-7766-07fc-3c7b-42b9e7ed5539 | 2 | {"TaskId":"da74b716-7766-07fc-3c7b-42b9e7ed5539","ClusterNam |

---

## apm_app_instance (约 50651 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | int | NO | PRI | NULL | auto_increment |
| sync_date | date | NO | MUL | 0000-00-00 |  |
| res_type | varchar(200) | NO |  |  |  |
| env | varchar(32) | NO |  |  |  |
| application | varchar(200) | NO | MUL |  |  |
| db_instance_id | varchar(200) | NO | MUL |  |  |
| sync_time | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| gmt_create | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| gmt_modify | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | sync_date | res_type | env | application | db_instance_id | sync_time | gmt_create | gmt_modify |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3945 | 2023-11-14 | acs_rds | csprd | mes-identify | rm-bp1grg1366z46xmo0 | 2023-11-14 12:00:03 | 2023-11-14 12:00:02 | 2023-11-14 12:00:02 |
| 3946 | 2023-11-14 | acs_rds | csprd | bigdata-dsp-admin | rm-bp1090n197w37h8o5 | 2023-11-14 12:00:04 | 2023-11-14 12:00:03 | 2023-11-14 12:00:03 |
| 3947 | 2023-11-14 | acs_rds | csprd | bigdata-dsp-core | rm-bp1090n197w37h8o5 | 2023-11-14 12:00:04 | 2023-11-14 12:00:03 | 2023-11-14 12:00:03 |

---

## apm_env (约 40 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| parent_name | varchar(200) | NO | MUL |  |  |
| name | varchar(200) | NO | UNI |  |  |
| description | varchar(200) | NO |  |  |  |
| sync_time | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| gmt_create | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| gmt_modify | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | parent_name | name | description | sync_time | gmt_create | gmt_modify |
| --- | --- | --- | --- | --- | --- | --- |
| 71 |  | prd | 生产环境 | 2025-07-03 00:00:00 | 2023-11-14 12:00:00 | 2025-07-03 00:00:00 |
| 72 | prd | csprd | 五彩石生产环境 | 2025-07-03 00:00:00 | 2023-11-14 12:00:00 | 2025-07-03 00:00:00 |
| 73 | prd | h5-prod | H5生产环境 | 2025-07-03 00:00:00 | 2023-11-14 12:00:00 | 2025-07-03 00:00:00 |

---

## ark_config (约 19 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| url | varchar(255) | NO | UNI |  |  |
| token | varchar(400) | NO |  |  |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | url | token | create_time | update_time |
| --- | --- | --- | --- | --- |
| 1 | https://pre-oa-ark.shizhuang-inc.com | eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIiLCJpc3MiOiJhcmsiLCJ0Y3VpIjo | 2024-02-01 11:34:34 | 2024-02-01 11:34:34 |
| 2 | https://pre-ark.poizonapp.com | eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIiLCJpc3MiOiJhcmsiLCJ0Y3VpIjo | 2024-02-01 11:34:38 | 2024-02-01 11:34:38 |
| 3 | https://ark.shizhuang-inc.com | eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIiLCJpc3MiOiJhcmsiLCJ0Y3VpIjo | 2024-02-01 11:34:41 | 2024-02-01 11:34:41 |

---

## ark_record (约 27 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| user_id | varchar(100) | NO | MUL |  |  |
| realname | varchar(100) | NO |  |  |  |
| type | int | NO |  | 0 |  |
| url | varchar(255) | NO |  |  |  |
| schema_id | bigint | NO | MUL | 0 |  |
| search_name | varchar(200) | NO |  |  |  |
| env_id | varchar(200) | NO |  |  |  |
| group_id | varchar(100) | NO |  |  |  |
| username | varchar(100) | NO |  |  |  |
| password | varchar(400) | NO | MUL |  |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | username | password | create_time | update_time | user_id | realname | type | url | schema_id | search_name | env_id | group_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | dw_onedba | ENC(e9vXbliXEUaoyAWeI13KJO5apYj4wt9/rkSwez7V0SM=) | 2023-09-15 10:23:48 | 2023-09-15 10:23:48 | 10006019 | 彭东稳 | 0 | https://sit-ark.shizhuang-inc.net | 6 | dw_onedba@rm-uf634hx581tbo18em.mysql.rds.aliyuncs.com:3306 [ | D1 | 0609 |
| 2 |  | ENC(e9vXbliXEUaoyAWeI13KJO5apYj4wt9/rkSwez7V0SM=) | 2023-09-15 10:24:37 | 2023-09-15 10:24:37 | 10006019 | 彭东稳 | 1 | https://sit-ark.shizhuang-inc.net | 0 |  | D1 | 0609 |
| 3 |  | ENC(e9vXbliXEUaoyAWeI13KJO5apYj4wt9/rkSwez7V0SM=) | 2023-09-15 11:40:08 | 2023-09-15 11:40:08 | 10006019 | 彭东稳 | 1 | https://sit-ark.shizhuang-inc.net | 0 |  | D1 | 0609 |

---

## audit_review_grade_history (约 19 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| sql_finger | varchar(256) | NO |  |  |  |
| sql_finger_print | text | YES |  | NULL |  |
| score | tinyint | NO |  | 0 |  |
| grade_state | tinyint | NO |  | 0 |  |
| remark | varchar(255) | NO |  |  |  |
| handled | tinyint | NO |  | 0 |  |
| statement | text | YES |  | NULL |  |
| tables | varchar(512) | NO |  |  |  |
| total | int | NO |  | 0 |  |
| max_rt | int | NO |  | 0 |  |
| max_return_rows | int | NO |  | 0 |  |
| min_return_rows | int | NO |  | 0 |  |
| present_time | bigint | NO |  | 0 |  |
| createTime | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| modify_time | bigint | NO |  | 0 |  |
| min_rt | int | NO |  | 0 |  |
| create_time | bigint | NO |  | 0 |  |
| instance_id | varchar(128) | NO |  |  |  |
| db | varchar(128) | NO |  |  |  |

**样例数据:**

| id | total | max_rt | max_return_rows | min_return_rows | present_time | createTime | modify_time | min_rt | create_time | instance_id | sql_finger | db | sql_finger_print | score | grade_state | remark | handled | statement | tables |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 19 | 1 | 0 | 0 | 0 | 20211215160000 | 2021-12-24 15:32:12 | 1645537016 | 0 | 1645537016 | rr-bp15ql0o2u01x8nty | 58B6B8E001A86F75 | hupu_du_community | select id,trend_id, title,c_title from trend_title where tre | 80 | 1 |  | 0 | select id,trend_id, title,c_title from trend_title where tre | `soar_review`.`trend_title` |
| 20 | 1 | 0 | 1 | 1 | 20211215160000 | 2021-12-24 15:32:13 | 1645537016 | 0 | 1645537016 | rr-bp15ql0o2u01x8nty | 427FF7EC3A020BBF | hupu_du_community | select count(*) from trendfav where lightuserid=? | 95 | 1 |  | 0 | select count(*) from trendfav where lightuserid='4824096' | `soar_review`.`trendfav` |
| 21 | 3 | 0 | 0 | 0 | 20211215160000 | 2021-12-24 15:32:13 | 1645537016 | 0 | 1645537016 | rr-bp15ql0o2u01x8nty | C63DAD0E0D273FC4 | hupu_du_community | select circle.* from circle_relation_trend inner join circle | 75 | 1 |  | 0 | select
                    circle.*
                from
    | `soar_review`.`circle_relation_trend`,`soar_review`.`circle` |

---

## audit_review_instances (约 2 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| db_instance_id | varchar(256) | NO | UNI |  |  |
| description | varchar(256) | NO |  |  |  |
| business_subdomain | varchar(256) | NO |  |  |  |
| mainbody | varchar(256) | NO |  |  |  |
| namespace | varchar(256) | NO |  |  |  |
| port | int | NO |  | 0 |  |
| connection_string | varchar(256) | NO |  |  |  |
| running_state | tinyint | NO |  | 0 |  |
| job_state | tinyint | NO |  | 0 |  |
| create_time | bigint | NO |  | 0 |  |
| modify_time | bigint | NO |  | 0 |  |
| remark | varchar(512) | NO |  |  |  |

**样例数据:**

| id | job_state | create_time | modify_time | remark | db_instance_id | description | business_subdomain | mainbody | namespace | port | connection_string | running_state |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 0 | 0 | 1702314000 | done at : 2023-12-12 01:00:00 | rm-uf6xriti4mg9309j8 | du-dev-57 | 质量平台 | shizhuang |  | 3306 | rm-uf6xriti4mg9309j8.mysql.rds.aliyuncs.com | 1 |
| 5 | 0 | 0 | 1702314000 | done at : 2023-12-12 01:00:00 | rr-bp15ql0o2u01x8nty | prd-wireless-community-main-read1-夏先洋 | 创新 | shizhuang |  | 3306 | rr-bp15ql0o2u01x8nty150.mysql.rds.aliyuncs.com | 1 |

---

## automatic_expansion_event (约 535 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| cluster_id | varchar(200) | NO | MUL |  |  |
| description | varchar(200) | NO |  |  |  |
| host | varchar(200) | NO | MUL |  |  |
| group_id | int | NO |  | 0 |  |
| expansion_status | int | NO |  | -1 |  |
| expansion_memory | float(64,2) | NO |  | -1.00 |  |
| failed_detail | varchar(200) | NO |  |  |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | update_time | cluster_id | description | host | group_id | expansion_status | expansion_memory | failed_detail | create_time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2024-06-26 16:09:29 | kvredis-3fb4ca7c91 |  | 10.49.40.2:6400,10.49.40.2:6403 | 2 | 2 | 0.50 | redis[ 10.49.40.2:6400 ] 设置内存失败 资源池初始化未完成，请稍后 | 2024-06-19 15:28:48 |
| 2 | 2024-06-19 15:28:50 | kvredis-3fb4ca7c91 |  | 10.49.40.2:6400,10.49.40.2:6403 | 2 | 2 | 0.50 | redis[ 10.49.40.2:6400 ] 设置内存失败 资源池初始化未完成，请稍后 | 2024-06-19 15:28:50 |
| 3 | 2024-06-19 15:28:50 | kvredis-3fb4ca7c91 |  | 10.49.40.2:6400,10.49.40.2:6403 | 2 | 2 | 0.50 | redis[ 10.49.40.2:6400 ] 设置内存失败 资源池初始化未完成，请稍后 | 2024-06-19 15:28:50 |

---

## automatic_expansion_rules (约 76 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| cluster_id | varchar(200) | NO | UNI |  |  |
| description | varchar(200) | NO |  |  |  |
| is_open | int | NO |  | 1 |  |
| memory_arr | varchar(32) | YES |  |  |  |
| refactor_arr | varchar(32) | YES |  |  |  |
| expansion_threshold | float(64,2) | NO |  | 80.00 |  |
| expansion_memory_threshold | float(64,2) | NO |  | 7.00 |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | update_time | cluster_id | description | is_open | memory_arr | refactor_arr | expansion_threshold | expansion_memory_threshold | create_time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2024-06-19 15:28:47 | kvredis-3fb4ca7c91 | bao_test | 1 | 3000,8000 | 1,0.5 | 80.00 | 8.00 | 2024-06-19 15:28:47 |
| 2 | 2024-06-24 16:08:45 | kvredis-ac40831c30 | lsf-test1 | 1 | 3000,8000 | 1,0.5 | 80.00 | 8.00 | 2024-06-24 16:08:45 |
| 3 | 2024-06-26 11:09:46 | kvredis-9f35f39679 | prd-smart_push实时个性化push-史世睿 | 1 | 3000,8000 | 1,0.5 | 80.00 | 8.00 | 2024-06-26 11:09:46 |

---

## commodity_channel_tab (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint unsigned | NO | PRI | NULL | auto_increment |
| active_title_start_time | datetime | NO |  | 1970-01-01 08:00:01 |  |
| redirect_url | varchar(512) | NO |  |  |  |

---

## commodity_channel_tab1 (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint unsigned | NO | PRI | NULL | auto_increment |
| active_title_start_time | datetime | YES |  | 1970-01-01 08:00:01 |  |
| redirect_url | varchar(512) | NO |  |  |  |

---

## create_huoshan_dts_order (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| task_uuid | varchar(36) | NO | UNI |  |  |
| task_name | varchar(64) | NO |  |  |  |
| task_type | varchar(64) | NO |  |  |  |
| project_name | varchar(64) | NO |  | default |  |
| charge_type | varchar(20) | NO |  |  |  |
| auto_start | tinyint | NO |  | 0 |  |
| region | varchar(30) | NO |  |  |  |
| traffic_spec | varchar(30) | NO |  | Standard |  |
| solution_type | varchar(20) | NO |  | MySQL2MySQL |  |
| err_max_retry_seconds | int | NO |  | 600 |  |
| enable_incr | tinyint | NO |  | 1 |  |
| incr_mysql_pos_datetime | datetime | YES |  | NULL |  |
| incr_mysql_pos_gtid | varchar(200) | NO |  |  |  |
| set_statement | varchar(200) | NO |  |  |  |
| primary_key_conflict_policy | varchar(50) | NO |  |  |  |
| src_endpoint_type | varchar(64) | NO |  |  |  |
| src_vpc_id | varchar(50) | NO |  |  |  |
| src_subnet_id | varchar(50) | NO |  |  |  |
| src_region | varchar(64) | NO |  |  |  |
| src_instance_id | varchar(30) | NO |  |  |  |
| src_description | varchar(200) | NO |  |  |  |
| src_host | varchar(200) | NO |  |  |  |
| src_port | int | NO |  | 3306 |  |
| src_username | varchar(64) | NO |  |  |  |
| src_password | varchar(64) | NO |  |  |  |
| std_endpoint_type | varchar(64) | NO |  |  |  |
| std_vpc_id | varchar(50) | NO |  |  |  |
| std_subnet_id | varchar(50) | NO |  |  |  |
| std_region | varchar(64) | NO |  |  |  |
| std_instance_id | varchar(30) | NO |  |  |  |
| std_description | varchar(200) | NO |  |  |  |
| std_host | varchar(200) | NO |  |  |  |
| std_port | int | NO |  | 3306 |  |
| std_username | varchar(64) | NO |  |  |  |
| std_password | varchar(64) | NO |  |  |  |
| created_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| updated_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| is_deleted | tinyint | NO |  | 0 |  |

---

## create_huoshan_dts_order_table_map (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| task_uuid | varchar(36) | NO | MUL |  |  |
| src_db_name | varchar(64) | NO | MUL | NULL |  |
| src_table_name | varchar(64) | NO |  |  |  |
| std_db_name | varchar(64) | NO |  | NULL |  |
| std_table_name | varchar(64) | NO |  |  |  |
| created_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| updated_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

---

## das_storage_analysis_result (约 26 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| db_instance_id | varchar(200) | NO | MUL |  |  |
| task_id | varchar(200) | NO |  |  |  |
| task_result | json | YES |  | NULL |  |

**样例数据:**

| id | db_instance_id | task_id | task_result |
| --- | --- | --- | --- |
| 1 | rm-bp17y8k1cf1v3od4j | bcfda03181d42aff9f55683d15a50804 | {"TaskId": "bcfda03181d42aff9f55683d15a50804", "TaskState":  |
| 2 | rm-bp17v45r2i9pg544q | 91232e0172570331ceb4b5410320f530 | {"TaskId": "91232e0172570331ceb4b5410320f530", "TaskState":  |
| 3 | rm-bp17y8k1cf1v3od4j | 3cf9ae3a3361874036e1fc3ea5aa4f5c | {"TaskId": "3cf9ae3a3361874036e1fc3ea5aa4f5c", "TaskState":  |

---

## das_storage_analysis_task (约 30 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| db_instance_id | varchar(200) | NO | MUL |  |  |
| task_id | varchar(200) | NO |  |  |  |
| task_type | varchar(30) | NO |  |  |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| finish_time | datetime | NO |  | 1970-01-01 00:00:00 | on update CURRENT_TIMESTAMP |
| task_progress | int | NO |  | 0 |  |
| task_finish | tinyint(1) | NO | MUL | 0 |  |
| task_state | varchar(20) | NO |  |  |  |
| schema_name | varchar(200) | NO |  |  |  |
| table_name | varchar(200) | NO |  |  |  |
| is_expired | tinyint | NO |  | 0 |  |

**样例数据:**

| id | task_state | schema_name | table_name | is_expired | db_instance_id | task_id | task_type | create_time | update_time | finish_time | task_progress | task_finish |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | FAILED |  |  | 0 | rm-bp17y8k1cf1v3od4j | 6e7ba07d110133d049a427cc186c2f08 | 分析全部库表 | 2025-04-29 15:25:24 | 2025-05-06 14:10:41 | 2025-05-06 14:10:41 | 100 | 1 |
| 2 | SUCCESS |  |  | 0 | rm-bp17y8k1cf1v3od4j | 319bda14a65a50dd744a1045af464a34 | 分析全部库表 | 2025-04-30 17:21:33 | 2025-05-09 18:55:39 | 2025-04-30 17:22:25 | 100 | 1 |
| 3 | SUCCESS |  |  | 0 | rm-bp17y8k1cf1v3od4j | 420e512374d44fdba92594fd0550e35f | 分析全部库表 | 2025-04-30 18:17:19 | 2025-04-30 18:17:54 | 2025-04-30 18:17:54 | 100 | 1 |

---

## full_review_grade_history (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| sql_finger | varchar(256) | NO |  |  |  |
| sql_finger_print | varchar(3000) | NO |  |  |  |
| score | tinyint | NO |  | 0 |  |
| statement | varchar(3000) | NO |  |  |  |
| tables | varchar(512) | NO |  |  |  |
| total | int | NO |  | 0 |  |
| max_rt | int | NO |  | 0 |  |
| max_return_rows | int | NO |  | 0 |  |
| min_return_rows | int | NO |  | 0 |  |
| present_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| createTime | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| modify_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |

---

## full_review_instances (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| instance_name | varchar(256) | NO |  |  |  |
| instance_id | varchar(64) | NO |  |  |  |
| running_state | tinyint | NO |  | 0 |  |
| job_state | tinyint | NO |  | 0 |  |
| create_time | bigint | NO |  | 0 |  |
| modify_time | bigint | NO |  | 0 |  |

---

## function_access (约 79 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| user_id | varchar(255) | NO | MUL |  |  |
| username | varchar(255) | NO |  |  |  |
| name | varchar(128) | NO |  |  |  |
| count | bigint | NO |  | 0 |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | user_id | username | name | count | create_time | update_time |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | 10006019 | pengdongwen | OrderDataExport | 5 | 2026-06-22 19:39:26 | 2026-06-23 11:02:21 |
| 11 | 10006019 | pengdongwen | Workplace | 57 | 2026-06-22 19:42:23 | 2026-06-25 14:54:35 |
| 14 | 10006019 | pengdongwen | Query | 120 | 2026-06-22 19:42:42 | 2026-06-24 21:59:37 |

---

## function_favorite (约 17 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| user_id | varchar(255) | NO | MUL |  |  |
| username | varchar(255) | NO |  |  |  |
| name | varchar(128) | NO |  |  |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | user_id | username | name | create_time | update_time |
| --- | --- | --- | --- | --- | --- |
| 18 | 10006019 | pengdongwen | OrderStructureDesign | 2026-06-22 19:57:01 | 2026-06-22 19:57:01 |
| 20 | 10006019 | pengdongwen | OrderDataChangeChunk | 2026-06-24 17:22:24 | 2026-06-24 17:22:24 |
| 21 | 10006019 | pengdongwen | OrderDataChange | 2026-06-24 17:22:26 | 2026-06-24 17:22:26 |

---

## idc_redis_promotion_inspection (约 28 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| date | varchar(20) | NO | MUL |  |  |
| db_instance_id | varchar(200) | NO |  |  |  |
| description | varchar(200) | YES |  |  |  |
| total_memory | decimal(10,2) | NO |  | 0.00 |  |
| total_used_memory | decimal(10,2) | NO |  | 0.00 |  |
| sharding_total_memory | decimal(10,2) | NO |  | 0.00 |  |
| sharding_total_used_memory | decimal(10,2) | NO |  | 0.00 |  |
| total_QPS | decimal(10,2) | NO |  | 0.00 |  |
| proxy_QPS | decimal(10,2) | NO |  | 0.00 |  |
| server_cpu | decimal(10,2) | NO |  | 0.00 |  |
| intranet_in | decimal(16,2) | NO |  | 0.00 |  |
| intranet_out | decimal(16,2) | NO |  | 0.00 |  |
| metric_time | int | NO |  | 0 |  |
| gmt_create | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| gmt_modify | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |

**样例数据:**

| id | proxy_QPS | server_cpu | intranet_in | intranet_out | metric_time | gmt_create | gmt_modify | date | db_instance_id | description | total_memory | total_used_memory | sharding_total_memory | sharding_total_used_memory | total_QPS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 208787 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 2023-11-17 14:12:09 | 2023-11-17 14:12:09 | 2023-11-16 | kvredis-fffc09c5d2 | 111 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 208788 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 2023-11-17 14:12:09 | 2023-11-17 14:12:09 | 2023-11-16 | kvredis-a7aeeaac4a | 111 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 208789 | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 2023-11-17 14:12:09 | 2023-11-17 14:12:09 | 2023-11-16 | kvredis-acef9805a8 | test341 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

---

## idc_redis_promotion_maxvalue_perday (约 1152 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| metric_date | date | NO | MUL | 1970-01-01 |  |
| db_instance_id | varchar(200) | NO | MUL |  |  |
| metric_name | varchar(200) | NO |  |  |  |
| value | decimal(16,2) | NO |  | 0.00 |  |
| metric_time | int | NO |  | 0 |  |
| gmt_create | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| gmt_modify | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |

**样例数据:**

| id | metric_date | db_instance_id | metric_name | value | metric_time | gmt_create | gmt_modify |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5670979 | 2023-11-16 | kvredis-fffc09c5d2 | MaxMemory | 0.00 | 0 | 2023-11-16 21:59:58 | 2023-11-16 21:59:58 |
| 5670980 | 2023-11-16 | kvredis-fffc09c5d2 | UsedMemory | 0.00 | 0 | 2023-11-16 21:59:58 | 2023-11-16 21:59:58 |
| 5670981 | 2023-11-16 | kvredis-fffc09c5d2 | ShardingMaxMemory | 0.00 | 0 | 2023-11-16 21:59:59 | 2023-11-16 21:59:59 |

---

## kv_employee (约 7 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| name | varchar(200) | NO | UNI |  |  |
| mobile | varchar(200) | NO |  |  |  |
| gmt_create | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| gmt_modify | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| mobilebak | varchar(200) | NO |  |  |  |
| lark_open_id | varchar(255) | NO |  |  |  |
| lark_user_id | varchar(200) | NO |  |  |  |
| user_role | int | NO |  | 0 |  |
| is_active | tinyint | NO |  | 1 |  |

**样例数据:**

| id | is_active | name | mobile | gmt_create | gmt_modify | mobilebak | lark_open_id | lark_user_id | user_role |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 罗代阳 | 18392638768 | 2025-01-12 20:19:01 | 2025-01-21 17:57:25 | 19392638768 | 32 | ou_678a8ccf307b7f2e6871575db02f82b7dddd | 6 |
| 2 | 1 | 罗明 | 18868818963 | 2025-01-12 20:20:34 | 2025-01-12 20:20:34 | 18868818963 | ou_e5e9f1c41ae7f5887c5b5a0665cb44ac | 10026081 | 6 |
| 3 | 1 | 张昀 | 13810395182 | 2025-01-12 20:20:41 | 2025-01-12 20:20:41 | 13810395182 | ou_04a2ff262dd4ba8594ffdaadd9b5ba9f | 10057633 | 6 |

---

## kv_resource (约 1 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | int | NO | PRI | NULL | auto_increment |
| host_ip | varchar(32) | NO |  |  |  |
| instance_amount | int | NO |  | 0 |  |
| host_cpu | int | NO |  | 0 |  |
| cpu_utilization | int | NO |  | 0 |  |
| cpu_load | int | NO |  | 0 |  |
| host_memory | int | NO |  | 0 |  |
| host_memory_rss | int | NO |  | 0 |  |
| host_memory_allocated | int | NO |  | 0 |  |
| max_instance_setting | int | NO |  | 0 |  |
| heartbeat | tinyint | NO |  | 0 |  |
| create_time | bigint | NO |  | 0 |  |
| modify_time | bigint | NO |  | 0 |  |
| is_valid | tinyint | NO |  | 0 |  |
| agent_port | int | NO |  | 50001 |  |

**样例数据:**

| id | max_instance_setting | heartbeat | create_time | modify_time | is_valid | agent_port | host_ip | instance_amount | host_cpu | cpu_utilization | cpu_load | host_memory | host_memory_rss | host_memory_allocated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 1 | 1 | 1 | 1 | 50001 | 127.0.0.1 | 2 | 1 | 1 | 1 | 1 | 1 | 1 |

---

## ob_cluster (约 2 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| origin | varchar(64) | NO |  | CREATED |  |
| creator | varchar(64) | YES |  | NULL |  |
| name | varchar(256) | NO | MUL | NULL |  |
| ob_version | varchar(32) | NO |  | NULL |  |
| vpc_id | bigint | NO |  | 1 |  |
| ob_cluster_id | bigint | NO |  | NULL |  |
| type | varchar(16) | NO |  | PRIMARY |  |
| architecture | varchar(128) | YES |  | NULL |  |
| rootserver_json | text | YES |  | NULL |  |
| rootserver_update_time | datetime(6) | NO |  | CURRENT_TIMESTAMP(6) | DEFAULT_GENERATED |
| status | varchar(64) | NO |  | CREATING |  |
| sync_status | varchar(32) | NO |  | VALID |  |
| operate_status | varchar(16) | NO |  | NORMAL |  |
| compaction_status | varchar(16) | YES |  | NULL |  |
| arbitration_service_id | bigint | YES |  | NULL |  |
| startup_parameters | text | YES |  | NULL |  |
| attributes_json | text | YES |  | NULL |  |
| start_time | datetime | YES |  | NULL |  |
| stop_time | datetime | YES |  | NULL |  |
| group_id | bigint | NO |  | 0 |  |
| snapshot_id | bigint | YES |  | 0 |  |
| package_operating_system | varchar(128) | YES |  | NULL |  |
| load_type | varchar(256) | YES |  | NULL |  |
| ob_start_time | datetime | YES |  | NULL |  |

**样例数据:**

| id | type | architecture | rootserver_json | rootserver_update_time | status | sync_status | operate_status | compaction_status | arbitration_service_id | startup_parameters | create_time | attributes_json | start_time | stop_time | group_id | snapshot_id | package_operating_system | load_type | ob_start_time | update_time | origin | creator | name | ob_version | vpc_id | ob_cluster_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | PRIMARY | NULL | {"ObCluster":"myocp","ObClusterId":1749130419,"ObRegion":"my | 2025-12-26 16:07:59.474120 | RUNNING | VALID | NORMAL | IDLE | NULL | NULL | 2025-07-21 11:27:57 | {"DataDiskPath":"/data/1","DiskPathStyle":"OBD","InstallPath | NULL | NULL | 1001 | 0 | NULL | NULL | 2025-07-21 11:28:40 | 2025-12-26 16:07:59 | TAKEN_OVER | admin | myocp | 4.2.1.8 | 1 | 1749130419 |
| 2 | PRIMARY | NULL | {"ObCluster":"archive","ObClusterId":
1749130421,"ObRegion": | 2025-12-26 16:09:40.517335 | RUNNING | VALID | NORMAL | IDLE | NULL | NULL | 2025-07-21 11:42:14 | {"DataDiskPath
":"/data","DiskPathStyle":"DEFAULT","InstallP | NULL | NULL | 1002 | 0 | el7 | NULL | 2025-07-21 11:42:56 | 2025-12-26 16:09:40 | TAKEN_OVER | admin | archive | 4.3.5.2 | 1 | 1749130421 |

---

## ob_tenant (约 10 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| creator | varchar(64) | YES |  | NULL |  |
| ob_tenant_id | bigint | NO |  | NULL |  |
| name | varchar(128) | NO |  | NULL |  |
| mode | varchar(64) | YES |  | MYSQL |  |
| cluster_id | bigint | NO | MUL | NULL |  |
| status | varchar(32) | NO |  | NULL |  |
| role | varchar(16) | NO |  | PRIMARY |  |
| primary_tenant_id | bigint | YES |  | NULL |  |
| log_transport_mode | varchar(16) | YES |  | NULL |  |
| is_locked | tinyint(1) | YES |  | 0 |  |
| is_read_only | tinyint(1) | YES |  | 0 |  |
| arbitration_status | varchar(32) | YES |  | NULL |  |
| primary_zone | varchar(128) | YES |  | NULL |  |
| zone_list | text | YES |  | NULL |  |
| locality | text | YES |  | NULL |  |
| service_name | varchar(255) | YES |  | NULL |  |
| service_name_status | varchar(64) | YES |  | NULL |  |
| description | text | YES |  | NULL |  |
| load_type | varchar(256) | YES |  | NULL |  |

**样例数据:**

| id | role | primary_tenant_id | log_transport_mode | is_locked | is_read_only | arbitration_status | primary_zone | zone_list | locality | service_name | create_time | service_name_status | description | load_type | update_time | creator | ob_tenant_id | name | mode | cluster_id | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | PRIMARY | NULL | NULL | 0 | 0 | DISABLED | RANDOM | zone1 | FULL{1}@zone1 | NULL | 2025-07-21 11:28:50 | NULL | NULL | NULL | 2025-07-21 11:28:50 | system | 1 | sys | MYSQL | 1 | NORMAL |
| 2 | PRIMARY | NULL | NULL | 0 | 0 | DISABLED | RANDOM | zone1 | FULL{1}@zone1 | NULL | 2025-07-21 11:28:50 | NULL | NULL | NULL | 0000-00-00 00:00:00 | system | 1002 | ocp_meta | MYSQL | 1 | NORMAL |
| 3 | PRIMARY | NULL | NULL | 0 | 0 | DISABLED | RANDOM | zone1 | FULL{1}@zone1 | NULL | 2025-07-21 11:28:50 | NULL | NULL | NULL | 2025-07-21 11:28:50 | system | 1004 | ocp_monitor | MYSQL | 1 | NORMAL |

---

## redis_key_parser_expired_key_count (约 27 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| instance_id | varchar(128) | NO | MUL | NULL |  |
| node_id | varchar(128) | NO |  |  |  |
| task_id | bigint | NO |  | NULL |  |
| key_amount | bigint | NO |  | 0 |  |
| key_expired_amount | bigint | NO |  | 0 |  |
| key_expired_never | bigint | NO |  | 0 |  |
| key_expired_between0_and1h | bigint | NO |  | 0 |  |
| key_expired_between1_and3h | bigint | NO |  | 0 |  |
| key_expired_between3_and12h | bigint | NO |  | 0 |  |
| key_expired_between12_and24h | bigint | NO |  | 0 |  |
| key_expired_between1_and2d | bigint | NO |  | 0 |  |
| key_expired_between3_and4d | bigint | NO |  | 0 |  |
| key_expired_between4_and7d | bigint | NO |  | 0 |  |
| key_expired_upper7d | bigint | NO |  | 0 |  |
| create_time | bigint | NO |  | 0 |  |
| modify_time | bigint | NO |  | 0 |  |
| key_expired_between2_and3d | bigint | NO |  | 0 |  |

**样例数据:**

| id | key_expired_between3_and12h | key_expired_between12_and24h | key_expired_between1_and2d | key_expired_between3_and4d | key_expired_between4_and7d | key_expired_upper7d | create_time | modify_time | key_expired_between2_and3d | instance_id | node_id | task_id | key_amount | key_expired_amount | key_expired_never | key_expired_between0_and1h | key_expired_between1_and3h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 387048 | 0 | 0 | 0 | 0 | 0 | 0 | 1723185160 | 1723185160 | 0 | kvredis-3fb4ca7c91 | 10.49.40.2:6400 | 1721152800879075 | 6509699 | 99 | 650000 | 9600 | 0 |
| 387049 | 0 | 0 | 0 | 0 | 0 | 0 | 1732260150 | 1732260150 | 0 | kvredis-393fd2e55d | 10.49.39.88:6400 | 1732260149861560 | 21314 | 0 | 60 | 21254 | 0 |
| 387050 | 0 | 0 | 0 | 0 | 0 | 0 | 1732260152 | 1732260152 | 0 | kvredis-393fd2e55d | 10.49.39.88:6401 | 1732260149861560 | 190 | 0 | 190 | 0 | 0 |

---

## redis_slb_acl (约 6 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | int | NO | PRI | NULL | auto_increment |
| acl_id | varchar(64) | NO |  | NULL |  |
| env_type | varchar(16) | NO | MUL | NULL |  |

**样例数据:**

| id | acl_id | env_type |
| --- | --- | --- |
| 1 | acl-uf6n6ulot82xhk3gwh04j | test |
| 2 | acl-bp1l1dmkr9aohbcwgtkbw | prd |
| 3 | acl-bp1yhc0vql2hufbzu3esq | prd |

---

## todo_record (约 14 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| user_id | varchar(255) | NO | MUL |  |  |
| username | varchar(255) | NO |  |  |  |
| todo_type | varchar(255) | NO |  |  |  |
| level | varchar(255) | NO |  |  |  |
| status_code | varchar(255) | NO |  |  |  |
| status_desc | varchar(255) | NO |  |  |  |
| content | json | YES |  | NULL |  |
| is_finished | int | NO |  | 0 |  |
| comment | varchar(2000) | NO |  |  |  |
| task_id | bigint | NO |  | 0 |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | comment | task_id | create_time | update_time | user_id | username | todo_type | level | status_code | status_desc | content | is_finished |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 测试数据 | 825 | 2022-07-04 11:13:15 | 2023-06-09 11:38:53 | 10006019 | 彭东稳 | tableComment | 正常 | completed | 已完成 | {"schemaId": 118169, "tableName": "delivery_category_report" | 1 |
| 3 | 测试数据 | 825 | 2022-07-04 11:13:15 | 2026-06-17 14:40:42 | 10006019 | 彭东稳 | tableComment | 正常 | waitingProcess | 待处理 | {"schemaId": 118169, "tableName": "delivery_category_report" | 0 |
| 26698 | 你的云数据库RDS版（RDS）实例rr-bp1xjrg6m3e7338i7昨日触发Instance_Switchover | 52380 | 2025-04-09 09:05:00 | 2025-04-09 09:42:46 | 10013895 | 佳祺(Jackie)｜王家琪 | inspectionAlert | 紧急 | completed | 已完成 | {"level": "紧急", "score": 3, "resType": "acs_rds", "alertTime | 1 |

---

## todo_record_detail (约 18 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| record_type | varchar(255) | NO |  |  |  |
| todo_id | bigint | NO | MUL | 0 |  |
| user_id | varchar(255) | NO |  |  |  |
| username | varchar(255) | NO |  |  |  |
| status_code | varchar(255) | NO |  |  |  |
| status_desc | varchar(255) | NO |  |  |  |
| comment | varchar(2000) | NO |  |  |  |
| is_finished | int | NO |  | 0 |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | create_time | update_time | record_type | todo_id | user_id | username | status_code | status_desc | comment | is_finished |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2022-07-04 11:13:15 | 2023-06-09 11:38:52 | handler | 1 | 10006019 | 彭东稳 | accepted | 已确认 |  | 1 |
| 2 | 2022-07-04 11:13:15 | 2023-06-09 11:38:52 | handler | 1 | 10006019 | 彭东稳 | waiting | 待确认 |  | 1 |
| 825 | 2023-06-09 11:38:52 | 2023-06-09 11:38:53 | handler | 1 | 10006019 | 彭东稳 | completed | 已完成 |  | 1 |

---

## app_profile_lists (约 1 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| app_id | varchar(256) | NO | UNI | NULL |  |
| analysed | tinyint | YES | MUL | NULL |  |
| engine | varchar(256) | YES |  | NULL |  |
| pt | datetime | YES |  | NULL |  |
| results | varchar(4096) | YES |  | NULL |  |
| diagnosis_tags | json | YES |  | NULL |  |
| created_at | datetime | YES |  | NULL |  |
| updated_at | datetime | YES |  | NULL |  |

**样例数据:**

| id | app_id | analysed | engine | pt | results | diagnosis_tags | created_at | updated_at |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3998302 | application_1743229280803_2591594 | 1 | spark | 2025-05-07 12:00:19 | [{"name":"slow_host","success":true,"message":"","duration": | null | 2025-05-08 00:02:08 | 2025-05-08 00:12:10 |

---

## auto_increment_column_day (约 541 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| collect_date | date | NO | MUL | NULL |  |
| db_instance_id | varchar(64) | NO | MUL |  |  |
| description | varchar(200) | NO |  |  |  |
| db_name | varchar(64) | NO |  |  |  |
| table_name | varchar(64) | NO |  |  |  |
| column_name | varchar(64) | NO |  |  |  |
| column_type | varchar(100) | NO |  |  |  |
| is_unsigned | varchar(20) | NO |  | NO |  |
| auto_increment_value | decimal(24,2) | NO |  | 0.00 |  |
| craeted_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| updated_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | auto_increment_value | craeted_time | updated_time | collect_date | db_instance_id | description | db_name | table_name | column_name | column_type | is_unsigned |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 126385446.00 | 2026-02-05 17:26:24 | 2026-02-05 17:26:24 | 2026-02-05 | rm-uf6e7tt4w809o579j | 测试环境 | dw_onedba | account | id | bigint | NO |
| 2 | 12.00 | 2026-02-05 17:26:24 | 2026-02-05 17:26:24 | 2026-02-05 | rm-uf6e7tt4w809o579j | 测试环境 | dw_onedba | account_department_manager | id | bigint | NO |
| 3 | 18.00 | 2026-02-05 17:26:24 | 2026-02-05 17:26:24 | 2026-02-05 | rm-uf6e7tt4w809o579j | 测试环境 | dw_onedba | account_open_api_token | id | bigint | NO |

---

## bigtable_counts (约 232 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| bigtablesize | varchar(32) | YES |  | NULL |  |
| counts | int | YES |  | NULL |  |
| collect_datatime | datetime | NO | MUL | NULL |  |

**样例数据:**

| id | bigtablesize | counts | collect_datatime |
| --- | --- | --- | --- |
| 175 | less10G | 1507517 | 2025-05-29 00:00:00 |
| 176 | 10G | 3435 | 2025-05-29 00:00:00 |
| 177 | 20G | 1530 | 2025-05-29 00:00:00 |

---

## bill_dept_product_cost_detail (约 97117 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | char(32) | NO | PRI | NULL |  |
| date | date | NO | MUL | NULL |  |
| mode | int | NO | MUL | NULL |  |
| instance | varchar(200) | YES |  | NULL |  |
| amount | double | NO |  | NULL |  |
| aliyun_product_id | varchar(100) | YES | MUL | NULL |  |
| app_id | varchar(128) | YES | MUL | NULL |  |
| dept_lv2_id | int | YES | MUL | NULL |  |
| dept_lv3_id | int | YES | MUL | NULL |  |
| account_id | varchar(50) | NO | MUL | 1816563541899700 |  |

**样例数据:**

| id | account_id | date | mode | instance | amount | aliyun_product_id | app_id | dept_lv2_id | dept_lv3_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 00002150d62c42929f2105b4c81c5b0c | 1816563541899700 | 2024-11-05 | 1 | rr-bp18n3e7h6qt713pl | 11.425806451612903 | rds | NULL | 94 | 5496 |
| 00031fa5b8bf4766bf2b0d7e480019ff | 1816563541899700 | 2024-12-02 | 1 | rm-bp1g109fgjgyz8ipy | 12.699354838709677 | rds | NULL | 210 | 215 |
| 000433aa4cf943b1bf24c85e199ab1a9 | 1816563541899700 | 2024-12-18 | 1 | rm-bp1w4xi5ak3pw9t6d | 43.56225806451613 | rds | NULL | 543 | 7490 |

---

## bpm_stack_stat (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| appkey | varchar(128) | NO | MUL |  |  |
| point_date | date | NO | MUL | 2000-01-01 |  |
| bpm_stack_id | varchar(128) | NO | MUL |  |  |
| user_id | varchar(20) | NO |  |  |  |
| code | varchar(20) | NO |  | NULL |  |
| version | varchar(56) | NO |  |  |  |
| log_count | int | NO |  | 0 |  |
| device_count | int | NO |  | 0 |  |
| last_stack_log_id | varchar(56) | NO |  |  |  |
| last_stack_info_id | varchar(56) | NO |  |  |  |
| last_stack_time | bigint | NO |  | 0 |  |
| time_point | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| time_line | int | NO |  | 0 |  |
| crash_type | int | NO |  | 0 |  |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| device_id | varchar(128) | NO |  |  |  |
| build_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| build_id | varchar(8) | NO |  |  |  |

---

## deploy_platform_message (约 192 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| project_name | varchar(256) | NO |  |  |  |
| project_id | int | NO |  | 0 |  |
| lang | varchar(256) | NO |  |  |  |
| grafana_alias | varchar(256) | NO |  |  |  |
| project_level | int | NO |  | 0 |  |
| description | varchar(256) | NO |  |  |  |
| env | varchar(256) | NO |  |  |  |
| git | varchar(256) | NO |  |  |  |
| branch | varchar(256) | NO |  |  |  |
| commit_id | varchar(256) | NO |  |  |  |
| department | varchar(256) | NO |  |  |  |
| username | varchar(256) | NO |  |  |  |
| business | varchar(256) | NO |  |  |  |
| task_id | int | NO |  | 0 |  |
| deploy_type | varchar(256) | NO |  |  |  |
| create_time | bigint | NO |  | 0 |  |
| modify_time | bigint | NO |  | 0 |  |

**样例数据:**

| id | branch | commit_id | department | username | business | task_id | deploy_type | create_time | modify_time | project_name | project_id | lang | grafana_alias | project_level | description | env | git |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | v2.5 | bd415056 |  | luoxiaoyong |  | 1 | docker | 0 | 0 | poizon-cloud-admin | 1511 | JAVA | poizon-cloud-admin | 3 | 得物云后台项目 | pre1 | git@pkg.shizhuang-inc.com:luoxiaoyong/poizon-cloud.git |
| 2 | v2.5 | bd415056 |  | luoxiaoyong |  | 1 | docker | 0 | 0 | poizon-cloud-admin | 1511 | JAVA | poizon-cloud-admin | 3 | 得物云后台项目 | pre1 | git@pkg.shizhuang-inc.com:luoxiaoyong/poizon-cloud.git |
| 3 | feature/v491_20220401_wujianfei/customer_claim | 493cb711 |  | wujianfei |  | 1 | ecs | 0 | 0 | risk-analysis-front | 480 | H5 | risk-analysis-front | 2 | 风控运营中心前端 | t1 | git@pkg.shizhuang-inc.com:risk/risk-electric-business/risk-a |

---

## dts_heartbeat (约 2 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| dts_id | varchar(64) | NO | UNI |  |  |
| dts_name | varchar(500) | NO |  |  |  |
| hb_db | varchar(100) | NO |  |  |  |
| hb_table | varchar(100) | NO |  |  |  |
| source_instance_id | varchar(64) | NO |  |  |  |
| source_instance_name | varchar(500) | NO |  |  |  |
| source_host | varchar(500) | NO |  |  |  |
| source_port | int | NO |  | 3306 |  |
| target_instance_id | varchar(64) | NO |  |  |  |
| target_instance_name | varchar(500) | NO |  |  |  |
| target_host | varchar(500) | NO |  |  |  |
| target_port | int | NO |  | 3306 |  |
| source_hb_time | datetime(6) | YES |  | NULL |  |
| target_hb_time | datetime(6) | YES |  | NULL |  |
| status | varchar(100) | NO |  |  |  |
| is_check_last_data | tinyint | NO |  | 0 |  |
| created_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| updated_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | target_instance_id | target_instance_name | target_host | target_port | source_hb_time | target_hb_time | status | is_check_last_data | created_time | updated_time | dts_id | dts_name | hb_db | hb_table | source_instance_id | source_instance_name | source_host | source_port |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | rm-uf6e7tt4w809o579j | rm-uf6e7tt4w809o579j | rm-uf6e7tt4w809o579j.mysql.rds.aliyuncs.com | 3306 | 2026-01-19 16:28:13.379841 | 2026-01-19 16:28:13.379841 | running | 0 | 2026-01-16 18:35:59 | 2026-01-19 16:28:13 | aaaaa | aaaaa_name | __dw_dba_heartbeat__ | hb_dts_dtszk5u1bmrz5u83xxx | rm-uf6e7tt4w809o579j | rm-uf6e7tt4w809o579j | rm-uf6e7tt4w809o579j.mysql.rds.aliyuncs.com | 3306 |
| 5 | rm-uf6e7tt4w809o579j | rm-uf6e7tt4w809o579j | rm-uf6e7tt4w809o579j.mysql.rds.aliyuncs.com | 3306 | 2026-01-19 16:28:13.379841 | 2026-01-19 16:28:13.379841 | running | 0 | 2026-01-19 15:57:42 | 2026-01-19 16:28:13 | bbbbb | bbbbb_name | __dw_dba_heartbeat__ | hb_dts_dtszk5u1bmrz5u83xxx | rm-uf6e7tt4w809o579j | rm-uf6e7tt4w809o579j | rm-uf6e7tt4w809o579j.mysql.rds.aliyuncs.com | 3306 |

---

## dw_onedba_test (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint unsigned | NO | PRI | NULL | auto_increment |
| create_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| modify_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| name | varchar(200) | NO |  |  |  |

---

## expansion_information (约 8 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| cluster_id | varchar(200) | NO | MUL | NULL |  |
| expansion_size | decimal(10,2) | NO |  | 0.00 |  |
| is_manual | tinyint(1) | YES |  | NULL |  |
| created_time | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | cluster_id | expansion_size | is_manual | created_time |
| --- | --- | --- | --- | --- |
| 1 | kvredis-0363047a6b | 5.00 | 1 | 2024-12-13 10:10:22 |
| 2 | kvredis-0363047a6b | 4.00 | 1 | 2024-12-13 10:35:44 |
| 3 | kvredis-0363047a6b | 2.00 | 1 | 2024-12-25 20:52:05 |

---

## export_record (约 27 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| user_id | varchar(100) | NO | MUL |  |  |
| username | varchar(100) | NO |  |  |  |
| unique_code | varchar(200) | NO |  |  |  |
| export_type | varchar(255) | NO |  |  |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | user_id | username | unique_code | export_type | create_time | update_time |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 10006019 | pengdongwen | 30e6e5f2-706c-429e-a265-1ac9623315d5 | csv | 2023-09-19 21:35:18 | 2023-09-19 21:35:18 |
| 2 | 10006019 | pengdongwen | 30e6e5f2-706c-429e-a265-1ac9623315d5 | csv | 2023-09-19 21:36:16 | 2023-09-19 21:36:16 |
| 3 | 10006019 | pengdongwen | 30e6e5f2-706c-429e-a265-1ac9623315d5 | insert | 2023-09-19 21:37:47 | 2023-09-19 21:37:47 |

---

## flink_cost_checkout (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| create_time | datetime(3) | NO |  | CURRENT_TIMESTAMP(3) | DEFAULT_GENERATED |
| modify_time | datetime(3) | NO |  | CURRENT_TIMESTAMP(3) | DEFAULT_GENERATED on update CURRENT_TIMESTAMP(3) |
| split_date | date | NO | MUL | NULL |  |
| paas_code | varchar(256) | NO |  | NULL |  |
| department_id | bigint | NO |  | NULL |  |
| instance_id | varchar(256) | NO |  | NULL |  |
| app_id | varchar(256) | NO |  |  |  |
| cluster_id | varchar(256) | NO |  |  |  |
| charge_spec | varchar(256) | NO |  |  |  |
| resource_usage | bigint | NO |  | NULL |  |
| region | varchar(32) | NO |  | 国内 |  |
| algo_scenes | varchar(1000) | YES |  | NULL |  |

---

## gitlab_project_list (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| group_name | varchar(128) | YES |  | NULL |  |
| project_name | varchar(128) | YES |  | NULL |  |
| project_id | int | YES | MUL | NULL |  |
| branch_name | varchar(128) | YES |  | NULL |  |
| file_path | varchar(512) | YES |  | NULL |  |
| create_time | bigint | NO |  | 0 |  |
| modify_time | bigint | NO |  | 0 |  |
| is_valid | tinyint | YES |  | 0 |  |
| task_stats | varchar(128) | NO |  |  |  |
| last_commit_id | varchar(128) | NO |  |  |  |
| git_url | varchar(256) | NO |  |  |  |
| mysql_host | varchar(128) | NO |  |  |  |
| mysql_port | int | NO |  | 3306 |  |
| pom_files | varchar(2048) | NO |  |  |  |
| mapper_path | varchar(256) | NO |  |  |  |
| poms | text | YES |  | NULL |  |
| compile_path | varchar(1024) | NO |  |  |  |
| pre_branch_name | varchar(128) | NO |  |  |  |
| branch_commit | varchar(128) | NO |  |  |  |
| last_branch_commit | varchar(128) | NO |  |  |  |
| business_domain | varchar(128) | NO |  |  |  |

---

## kefu_inspection_task_score_214 (约 1 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint unsigned | NO | PRI | NULL | auto_increment |
| create_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| modify_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| task_id | bigint unsigned | NO | MUL | 0 |  |
| root_id | bigint unsigned | NO |  | 0 |  |
| category_id | bigint unsigned | NO |  | 0 |  |
| item_id | bigint unsigned | NO |  | 0 |  |
| score | decimal(10,2) | NO |  | 0.00 |  |
| bpo_flag | tinyint | NO |  | 0 |  |
| qc_flag | tinyint | NO |  | 0 |  |
| auto_score_deduct | decimal(10,2) | NO |  | 0.00 |  |
| match_index | text | YES |  | NULL |  |

**样例数据:**

| id | qc_flag | auto_score_deduct | match_index | create_time | modify_time | task_id | root_id | category_id | item_id | score | bpo_flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1052745 | 0 | 1.00 | [{"autoMatch":true,"bpoFlag":false,"checked":true,"manualFix | 2024-03-08 17:09:33 | 2024-03-08 17:09:33 | 10373005526 | 1000000 | 1000002 | 135 | 0.00 | 0 |

---

## meta_layer (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | int | NO | PRI | NULL | auto_increment |
| m_name | varchar(128) | NO | UNI | NULL |  |
| m_type | varchar(128) | NO |  | NULL |  |
| m_status | char(255) | NO |  | NULL |  |
| m_desc | varchar(128) | NO |  |  |  |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| last_update_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| createdby | varchar(100) | YES |  | NULL |  |
| modifiedby | varchar(100) | YES |  | NULL |  |
| config_id | int | NO |  | 0 |  |
| pipeline_id | int | NO |  | 0 |  |
| batch_id | int | NO |  | 0 |  |
| ext_info | varchar(1000) | NO |  |  |  |

---

## moye_employees_offline (约 2 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| employee_id | int | NO | PRI | NULL | auto_increment |
| first_name | varchar(50) | NO |  | NULL |  |
| last_name | varchar(50) | NO |  | NULL |  |
| email | varchar(100) | NO | UNI | NULL |  |
| hire_date | date | NO |  | NULL |  |
| salary | decimal(10,2) | YES |  | 0.00 |  |

**样例数据:**

| employee_id | first_name | last_name | email | hire_date | salary |
| --- | --- | --- | --- | --- | --- |
| 1 | John | Doe | john.doe@example.com | 2023-01-15 | 60000.00 |
| 2 | Jane | Smith | jane.smith@example.com | 2023-02-01 | 65000.00 |

---

## proxy_docker_spec (约 70 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| spec_id | bigint | YES |  | NULL |  |
| created_at | text | YES |  | NULL |  |
| updated_at | text | YES |  | NULL |  |
| deleted_at | double | YES |  | NULL |  |
| description | text | YES |  | NULL |  |
| limit_cpu | text | YES |  | NULL |  |
| limit_mem | text | YES |  | NULL |  |
| req_cpu | text | YES |  | NULL |  |
| req_mem | text | YES |  | NULL |  |
| spec_type | text | YES |  | NULL |  |
| env_type | varchar(10) | YES |  | NULL |  |
| id | int | NO | PRI | NULL | auto_increment |

**样例数据:**

| spec_id | spec_type | env_type | id | created_at | updated_at | deleted_at | description | limit_cpu | limit_mem | req_cpu | req_mem |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10 | limit | test | 1 | NULL | 2023-05-09 10:00:57.946 | NULL | 4C16G(limit) | 4000m | 16Gi | 500m | 12Gi |
| 14 | limit | test | 2 | NULL | 2022-06-17 15:00:11.728 | NULL | 4C4G(limit) | 4000m | 4Gi | 500m | 1Gi |
| 15 | limit | test | 3 | NULL | 2023-06-27 18:19:58.354 | NULL | 4C8G(limit) | 4000m | 8Gi | 500m | 6Gi |

---

## queue_plan_natural_time (约 96 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | int | NO | PRI | NULL | auto_increment |
| create_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| modify_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| plan_id | int | NO | MUL | NULL |  |
| plan_hour | varchar(4) | YES |  | NULL |  |
| time_tag | varchar(128) | YES |  | NULL |  |

**样例数据:**

| id | create_time | modify_time | plan_id | plan_hour | time_tag |
| --- | --- | --- | --- | --- | --- |
| 1 | 2026-03-23 21:12:16 | 2026-03-23 21:12:16 | 23 | 00 | workday |
| 2 | 2026-03-23 21:12:16 | 2026-03-23 21:12:16 | 24 | 01 | workday |
| 3 | 2026-03-23 21:12:16 | 2026-03-23 21:12:16 | 25 | 02 | workday |

---

## rds_max30min_avg_cpu_usage (约 126 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| date | varchar(20) | NO | MUL |  |  |
| db_instance_id | varchar(200) | NO |  |  |  |
| description | varchar(200) | NO |  |  |  |
| avg_cpu_usage | decimal(10,2) | NO |  | 0.00 |  |
| avg_cpu_times | int | NO |  | 0 |  |
| max_cpu_usage | decimal(10,2) | NO |  | 0.00 |  |
| max_cpu_times | int | NO |  | 0 |  |
| avg_iops | decimal(10,2) | NO |  | 0.00 |  |
| avg_iops_times | int | NO |  | 0 |  |
| max_iops | decimal(10,2) | NO |  | 0.00 |  |
| max_iops_times | int | NO |  | 0 |  |
| gmt_create | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| gmt_modify | timestamp | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | avg_iops_times | max_iops | max_iops_times | gmt_create | gmt_modify | date | db_instance_id | description | avg_cpu_usage | avg_cpu_times | max_cpu_usage | max_cpu_times | avg_iops |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 255 | 13 | 0.00 | 0 | 2024-10-23 11:51:07 | 2024-10-23 11:51:07 | 2024-10-22 | rr-bp1w1edi20ce9ybdf | prd-商品-基础-基础C端读-陈康贤 | 0.00 | 0 | 0.00 | 0 | 53.00 |
| 256 | 13 | 0.00 | 0 | 2024-10-23 11:51:07 | 2024-10-23 11:51:07 | 2024-10-22 | rm-bp12y0llr941ko1x5 | prd-交易平台-timeout_3-曾庆勇 | 0.00 | 0 | 0.00 | 0 | 54.00 |
| 257 | 12 | 0.00 | 0 | 2024-10-23 11:51:07 | 2024-10-23 11:51:07 | 2024-10-22 | rm-bp16d4z087w3ie0yx | prd-交易平台-timeout_1-曾庆勇 | 0.00 | 0 | 0.00 | 0 | 53.00 |

---

## recover_rule (约 2 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | int | NO | PRI | NULL | auto_increment |
| app_name | varchar(255) | YES | MUL | NULL |  |
| rule_name | varchar(255) | YES |  | NULL |  |
| level | varchar(255) | YES |  | NULL |  |
| script_path | varchar(255) | YES |  | NULL |  |
| is_active | varchar(100) | YES |  | NULL |  |

**样例数据:**

| id | app_name | rule_name | level | script_path | is_active |
| --- | --- | --- | --- | --- | --- |
| 1 | k8s-prd-standard-hz-3 | 自建StarRocks-容器Pod-磁盘使用率-通用-白天 | 中危 | /opt/apps/bigdata-sre-monitor-enhance/scripts/starrocks_moni | true |
| 2 | k8s-prd-standard-hz-3 | 自建StarRocks-容器Pod-磁盘使用率-通用-白天 | 高危 | /opt/apps/bigdata-sre-monitor-enhance/scripts/starrocks_moni | true |

---

## sbtest1 (约 1000001 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | int | NO | PRI | NULL | auto_increment |
| k | int | NO | MUL | 0 |  |
| c | char(120) | NO |  |  |  |
| pad | char(60) | NO |  |  |  |

**样例数据:**

| id | k | c | pad |
| --- | --- | --- | --- |
| 1 | 498670 | 31451373586-15688153734-79729593694-96509299839-83724898275- | 98996621624-36689827414-04092488557-09587706818-65008859162 |
| 2 | 497778 | 21472970079-70972780322-70018558993-71769650003-09270326047- | 04776826683-45880822084-77922711547-29057964468-76514263618 |
| 3 | 498956 | 49376827441-24903985029-56844662308-79012577859-40518387141- | 26843035807-96849339132-53943793991-69741192222-48634174017 |

---

## sbtest2 (约 1000000 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | int | NO | PRI | NULL | auto_increment |
| k | int | NO | MUL | 0 |  |
| c | char(120) | NO |  |  |  |
| pad | char(60) | NO |  |  |  |

**样例数据:**

| id | k | c | pad |
| --- | --- | --- | --- |
| 1 | 504616 | 43033802100-77764610845-39799112869-39522082157-29991343351- | 95980075736-25797396575-06969310132-10655251718-72185519249 |
| 2 | 503857 | 76306723138-65475533272-75387439533-24814990765-46240013424- | 96730261334-40420286195-59727642680-29068251337-21208591100 |
| 3 | 459563 | 95511505952-67827527851-32245183764-01321888676-12935581940- | 60787675634-88696102862-47382723687-55751123510-43680810947 |

---

## sign_month_rule (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint unsigned | NO | PRI | NULL | auto_increment |
| name | varchar(64) | NO |  |  |  |
| note | varchar(1024) | NO |  |  |  |
| late_rule | varchar(1024) | NO |  |  |  |
| vacation_rule | varchar(1024) | NO |  |  |  |
| overtime_rule | varchar(1024) | NO |  |  |  |
| create_at | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_at | datetime | YES |  | NULL | on update CURRENT_TIMESTAMP |
| create_user | varchar(31) | NO |  |  |  |
| modify_user | varchar(31) | NO |  |  |  |
| is_delete | tinyint(1) | NO |  | 0 |  |
| delete_at | datetime(6) | YES |  | NULL |  |

---

## sls_log_config (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| name | varchar(100) | NO | UNI | NULL |  |
| description | varchar(255) | YES |  | NULL |  |
| a_k | varchar(100) | NO |  | NULL |  |
| a_s | varchar(100) | NO |  | NULL |  |
| endpoint | varchar(255) | NO |  | NULL |  |
| project | varchar(100) | NO |  | NULL |  |
| logstore | varchar(100) | NO |  | NULL |  |
| consumer_group_name | varchar(100) | NO |  | NULL |  |
| created_at | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| updated_at | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

---

## temp_column (约 0 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| instance_id | varchar(100) | NO |  | NULL |  |
| schema_name | varchar(100) | NO |  | NULL |  |
| table_name | varchar(100) | NO |  | NULL |  |
| column_name | varchar(100) | NO |  | NULL |  |
| column_comment | varchar(100) | YES |  | NULL |  |

---

## weekly_report_recipients_v2 (约 3 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| realname | varchar(200) | NO |  | NULL |  |
| feishu_user_id | varchar(200) | NO | MUL | NULL |  |
| email | varchar(200) | NO |  | NULL |  |
| created_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| updated_time | datetime | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |
| is_enabled | tinyint | NO |  | 1 |  |
| is_cc | tinyint | NO |  | 0 |  |

**样例数据:**

| id | realname | feishu_user_id | email | created_time | updated_time | is_enabled | is_cc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 袁泽文 | 10058467 | yuanzewen@shizhuang-inc.com | 2024-08-13 17:29:30 | 2024-08-13 17:29:30 | 1 | 0 |
| 5 | 陈浩 | 10046675 | chenhao1023@shizhuang-inc.com | 2024-08-26 14:33:15 | 2024-08-26 15:59:14 | 1 | 1 |
| 6 | 罗代阳 | 10055889 | luodaiyang@shizhuang-inc.com | 2024-08-26 15:08:14 | 2024-08-26 17:07:55 | 0 | 1 |

---

## xuanlin_task_record (约 1 行)

| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |
|------|------|---|---|--------|------|
| id | bigint | NO | PRI | NULL | auto_increment |
| job_id | varchar(400) | NO | UNI | 0 |  |
| user_id | varchar(400) | NO |  | 0 |  |
| order_id | bigint | NO |  | 0 |  |
| count | int | NO |  | 1 |  |
| content | text | YES |  | NULL |  |
| message | text | YES |  | NULL |  |
| create_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| update_time | datetime | NO | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

**样例数据:**

| id | job_id | user_id | order_id | count | content | message | create_time | update_time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 12ec1cf5-1efd-4778-bce1-5b14e6912a0f | 10036968 | 20017 | 1 | {"apiVersion":"app/v1","source":"Xuanlin","kind":"MYSQL","jo |  | 2025-05-08 16:07:16 | 2025-05-08 16:07:21 |

---

