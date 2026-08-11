# conftest.py — pytest 启动时加载项目根 .env
"""Load .env into os.environ before any test module imports app.config.

Without this, Settings(...) with env_file=".env" resolves .env relative to
CWD (unreliable under pytest), and tests that gate on os.environ (e.g.
test_real_engine_streams skipif LLM_API_KEY) never see .env values.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


def pytest_configure(config) -> None:
    """Hook: runs once at pytest startup, before test collection."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        print(f"[conftest] .env 不存在（{env_path}），跳过加载")
        return

    # 加载前记录：已显式设置的环境变量名（这些不应被 .env 覆盖）
    already_set = {k for k in os.environ if k and "=" not in k}

    loaded = load_dotenv(env_path, override=False)

    # 统计 .env 中实际生效的键（排除 comment 与空行）
    applied = 0
    skipped = 0
    with open(env_path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key = line.split("=", 1)[0].strip()
            if key in already_set:
                skipped += 1
            else:
                applied += 1

    print(
        f"[conftest] 已加载 {env_path.name}："
        f"{applied} 个变量生效"
        f"{f'，{skipped} 个被已有环境变量覆盖' if skipped else ''}"
        f"（loaded={loaded}）"
    )
