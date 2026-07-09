"""
导出 Langfuse trace 中所有 observation 的完整 input/output。

Langfuse 后台"导出 JSON"用的是旧 Public API，不包含 observation 级别的 input/output。
但 SDK 的 api.trace.get() 会返回完整的 observations（含 input/output）。

用法:
    python scripts/export_trace.py <trace_id>
    python scripts/export_trace.py <trace_id> --type TOOL     # 只导出工具调用
    python scripts/export_trace.py <trace_id> --type GENERATION  # 只导出 LLM 调用
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from langfuse import Langfuse


def export(trace_id: str, filter_type: str | None = None):
    lf = Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
        host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
    )

    # api.trace.get() 返回的 trace 中已包含所有 observations 的完整 input/output
    trace = lf.api.trace.get(trace_id)
    trace_url = lf.get_trace_url(trace_id=trace_id)

    print(f"Trace: {trace.name}")
    print(f"URL: {trace_url}")

    all_obs = trace.observations or []
    print(f"共 {len(all_obs)} 个 observation\n")

    result = []
    for obs in all_obs:
        t = obs.type
        name = obs.name
        if filter_type and t != filter_type:
            continue

        item = {
            "id": obs.id,
            "type": t,
            "name": name,
            "start_time": str(obs.start_time) if obs.start_time else None,
            "end_time": str(obs.end_time) if obs.end_time else None,
            "latency": obs.latency,
            "input": obs.input,
            "output": obs.output,
            "metadata": obs.metadata,
            "model": obs.model,
        }
        result.append(item)

        has_in = "✓" if item["input"] else "✗"
        has_out = "✓" if item["output"] else "✗"
        print(f"  [{len(result)}] {t}:{name}  input={has_in}  output={has_out}")

    # 写出
    out = f"trace_{trace_id}_full.json"
    Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print(f"\n✅ 导出到 {out}，共 {len(result)} 条")

    # 统计
    has_input = sum(1 for r in result if r["input"])
    has_output = sum(1 for r in result if r["output"])
    print(f"   有 input: {has_input}, 有 output: {has_output}")

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/export_trace.py <trace_id> [TOOL|GENERATION]")
        print("示例: python scripts/export_trace.py 9beec05b751766ae1fe35f7f5016331d")
        print("      python scripts/export_trace.py 9beec05b751766ae1fe35f7f5016331d TOOL")
        sys.exit(1)

    trace_id = sys.argv[1]
    filter_type = sys.argv[2] if len(sys.argv) > 2 else None
    export(trace_id, filter_type)