"""
从 OneDBA 平台拉取真实数据库 schema 信息（修正版）。
- 正确解析 OneDBA 的 columnNames(columnNames[i].title = 真实字段名) + columnDatas 格式
- 跳过 _idx_ 和 rowKey
- 537 张表太多，先拉表名列表，按业务前缀分组，再逐表 DESCRIBE + 采样
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

# ── 配置 ──────────────────────────────────────────────
BASE_URL = "https://onedba.shizhuang-inc.com"
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VybmFtZSI6IjEwMTA4NDczIiwiZXhwIjo1MzgxNjcxNjg2LCJpc3MiOiJPbmVEQkEifQ.VGbW1pNmUncxSNPsqX3R_oGLqc97wkMw3Vs1nN4z4zA"
TIMEOUT = 30.0
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "onedba_schema"

# 主目标 schema
TARGET_SCHEMA_ID = 65938636
TARGET_SCHEMA_NAME = "dw_onedba"


def headers():
    return {"accessToken": ACCESS_TOKEN, "Content-Type": "application/json"}


async def list_databases(client: httpx.AsyncClient, env_type: str = "test") -> list[dict]:
    """列出所有可用的数据库 schema。"""
    url = f"{BASE_URL}/api/external/v1/agent/instance/schema/user/list"
    params = {
        "queryType": "select",
        "page": 1,
        "size": 100,
        "envType": env_type,
        "instanceType": "acs_rds",
        "mainBody": "shizhuang",
    }
    resp = await client.get(url, headers=headers(), params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") not in (0, "0", None):
        print(f"  [ERROR] list_databases failed: {payload.get('message')}", file=sys.stderr)
        return []
    return (payload.get("data") or {}).get("items") or []


async def exec_sql(client: httpx.AsyncClient, schema_id: int, sql: str) -> dict:
    """在指定 schema 上执行 SQL。"""
    url = f"{BASE_URL}/api/external/v1/agent/query"
    body = {"schemaId": schema_id, "sqlText": sql, "queryTimeout": 30}
    resp = await client.post(url, headers=headers(), json=body, timeout=TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") not in (0, "0", None):
        return {"error": payload.get("message", "unknown")}
    return payload.get("data") or {}


def parse_onedba_result(data: dict) -> list[dict]:
    """
    正确解析 OneDBA 返回格式。

    OneDBA 返回结构:
      columnNames: [{key: "_idx_", title: "序号"}, {key: "col_1", title: "Tables_in_dw_onedba"}, ...]
      columnDatas: [{_idx_: 1, col_1: "account", rowKey: 1}, ...]

    转换后:
      用 title 作为字段名，跳过 _idx_ 和 rowKey
      → [{"Tables_in_dw_onedba": "account"}, ...]
    """
    col_names = data.get("columnNames") or []
    col_datas = data.get("columnDatas") or []
    if not col_names:
        return []

    # 构建 key → title 映射，跳过 _idx_
    key_to_title = {}
    for c in col_names:
        key = c.get("key", "")
        if key == "_idx_":
            continue
        title = c.get("title") or c.get("field") or key
        key_to_title[key] = title

    rows = []
    for row in col_datas:
        parsed = {}
        for key, value in row.items():
            if key in ("_idx_", "rowKey"):
                continue
            title = key_to_title.get(key, key)
            parsed[title] = value
        if parsed:
            rows.append(parsed)
    return rows


async def get_table_names(client: httpx.AsyncClient, schema_id: int) -> list[str]:
    """获取所有表名。"""
    data = await exec_sql(client, schema_id, "SHOW TABLES")
    if "error" in data:
        return []
    rows = parse_onedba_result(data)
    names = []
    for row in rows:
        # SHOW TABLES 返回的第一列（非 _idx_）就是表名
        for v in row.values():
            if v:
                names.append(str(v))
            break
    return names


async def describe_table(client: httpx.AsyncClient, schema_id: int, table_name: str) -> dict:
    """获取表结构 + 样例数据 + 行数。"""
    result = {"table_name": table_name}

    # DESCRIBE
    desc_data = await exec_sql(client, schema_id, f"DESCRIBE `{table_name}`")
    if "error" not in desc_data:
        result["columns"] = parse_onedba_result(desc_data)
    else:
        result["columns"] = []
        result["describe_error"] = desc_data["error"]

    # 行数
    count_data = await exec_sql(client, schema_id, f"SELECT COUNT(*) AS cnt FROM `{table_name}`")
    if "error" not in count_data:
        count_rows = parse_onedba_result(count_data)
        result["total_rows"] = count_rows[0].get("cnt", "?") if count_rows else "?"
    else:
        result["total_rows"] = "?"

    # 采样 3 行
    sample_data = await exec_sql(client, schema_id, f"SELECT * FROM `{table_name}` LIMIT 3")
    if "error" not in sample_data:
        result["sample_data"] = parse_onedba_result(sample_data)
    else:
        result["sample_data"] = []

    return result


def group_tables_by_prefix(table_names: list[str]) -> dict[str, list[str]]:
    """按表名前缀分组，帮助识别业务域。"""
    groups = {}
    for name in table_names:
        # 取第一个 _ 之前的部分作为前缀
        parts = name.split("_")
        prefix = parts[0] if len(parts) > 1 else name
        groups.setdefault(prefix, []).append(name)
    # 按组大小降序
    return dict(sorted(groups.items(), key=lambda x: -len(x[1])))


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient() as client:
        # ── Step 1: 列出所有数据库 ──
        print("=" * 60)
        print("Step 1: 列出所有可用数据库")
        print("=" * 60)

        dbs = await list_databases(client, env_type="test")
        if not dbs:
            print("没有找到可用数据库")
            return

        for db in dbs:
            print(f"  - {db.get('schemaName')} @ {db.get('instanceName')} "
                  f"(id={db.get('schemaId')}, env={db.get('envType')}, "
                  f"select={db.get('selectPriv')})")

        # ── Step 2: 获取目标 schema 的表名列表 ──
        print(f"\n{'=' * 60}")
        print(f"Step 2: 获取 {TARGET_SCHEMA_NAME} (id={TARGET_SCHEMA_ID}) 的表名列表")
        print("=" * 60)

        all_table_names = await get_table_names(client, TARGET_SCHEMA_ID)
        print(f"  共 {len(all_table_names)} 张表")

        # 按前缀分组
        groups = group_tables_by_prefix(all_table_names)
        print(f"\n  按前缀分组（共 {len(groups)} 个前缀）:")
        for prefix, tables in groups.items():
            print(f"    [{prefix}] ({len(tables)} 张表): {', '.join(tables[:5])}{'...' if len(tables) > 5 else ''}")

        # 保存完整表名列表
        table_list_file = OUTPUT_DIR / "all_table_names.json"
        with open(table_list_file, "w", encoding="utf-8") as f:
            json.dump({"total": len(all_table_names), "groups": groups, "all_names": all_table_names},
                      f, ensure_ascii=False, indent=2)
        print(f"\n  表名列表已保存到: {table_list_file}")

        # ── Step 3: 选择有业务意义的表进行详细拉取 ──
        # 跳过纯系统/配置表，优先选择有业务含义的表
        # 先拉取每个前缀的前几张表来了解结构
        tables_to_describe = []

        # 策略：每个前缀取前 3 张表，但排除明显是系统/日志/历史的表
        skip_prefixes = {"x", "s", "b", "q", "w"}  # 单字母前缀通常是系统表
        for prefix, tables in groups.items():
            if prefix in skip_prefixes and len(prefix) == 1:
                continue
            # 每个前缀最多取 3 张
            for t in tables[:3]:
                tables_to_describe.append(t)

        # 去重
        tables_to_describe = list(dict.fromkeys(tables_to_describe))

        print(f"\n{'=' * 60}")
        print(f"Step 3: 详细拉取 {len(tables_to_describe)} 张表的结构")
        print("=" * 60)

        all_tables_info = []
        for i, tbl in enumerate(tables_to_describe):
            print(f"  [{i+1}/{len(tables_to_describe)}] {tbl} ...")
            info = await describe_table(client, TARGET_SCHEMA_ID, tbl)
            all_tables_info.append(info)

        # ── Step 4: 保存结果 ──
        output_file = OUTPUT_DIR / "onedba_schema_detail.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({
                "schema_id": TARGET_SCHEMA_ID,
                "schema_name": TARGET_SCHEMA_NAME,
                "total_tables": len(all_table_names),
                "described_tables": len(all_tables_info),
                "tables": all_tables_info,
            }, f, ensure_ascii=False, indent=2)
        print(f"\n  详细 schema 已保存到: {output_file}")

        # 生成 Markdown 摘要
        md_file = OUTPUT_DIR / "onedba_schema_detail.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(f"# OneDBA Schema 详细摘要\n\n")
            f.write(f"- 数据库: {TARGET_SCHEMA_NAME} @ dw-onedba-t1\n")
            f.write(f"- Schema ID: {TARGET_SCHEMA_ID}\n")
            f.write(f"- 总表数: {len(all_table_names)}\n")
            f.write(f"- 已拉取详情: {len(all_tables_info)} 张表\n\n")
            f.write("---\n\n")

            for tbl in all_tables_info:
                f.write(f"## {tbl['table_name']} (约 {tbl['total_rows']} 行)\n\n")

                if tbl.get("describe_error"):
                    f.write(f"**错误**: {tbl['describe_error']}\n\n")
                    continue

                if tbl["columns"]:
                    f.write("| 字段 | 类型 | 空 | 键 | 默认值 | 额外 |\n")
                    f.write("|------|------|---|---|--------|------|\n")
                    for col in tbl["columns"]:
                        f.write(f"| {col.get('Field', '')} "
                                f"| {col.get('Type', '')} "
                                f"| {col.get('Null', '')} "
                                f"| {col.get('Key', '')} "
                                f"| {str(col.get('Default', ''))} "
                                f"| {col.get('Extra', '')} |\n")
                    f.write("\n")

                if tbl["sample_data"]:
                    f.write("**样例数据:**\n\n")
                    sample_keys = list(tbl["sample_data"][0].keys())
                    f.write("| " + " | ".join(sample_keys) + " |\n")
                    f.write("| " + " | ".join(["---"] * len(sample_keys)) + " |\n")
                    for row in tbl["sample_data"]:
                        vals = [str(row.get(k, ""))[:60] for k in sample_keys]
                        f.write("| " + " | ".join(vals) + " |\n")
                    f.write("\n")

                f.write("---\n\n")

        print(f"  Markdown 摘要已保存到: {md_file}")


if __name__ == "__main__":
    asyncio.run(main())
