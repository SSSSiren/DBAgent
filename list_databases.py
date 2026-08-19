import json
import urllib.request

# Try to read config from skill directory
config_path = "/Users/admin/.claude/skills/onedba-sql-console/config.json"
token = None

try:
    with open(config_path, "r") as f:
        config = json.load(f)
        token = config.get("onedba_access_token", "")
except Exception as e:
    print(f"Config read error: {e}")

if not token:
    print("ERROR: Could not find access token. Please set ONEDBA_ACCESS_TOKEN env variable or add onedba_access_token to config.json")
    exit(1)

url = "https://onedba.shizhuang-inc.com/onedba/api/v1/instance/schema/user/list?queryType=select&instanceType=acs_rds&mainBody=shizhuang&envType=test&page=1&size=30"

req = urllib.request.Request(url)
req.add_header("accessToken", token)
req.add_header("env", "prd")

try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode("utf-8"))
        print(json.dumps(data, indent=2, ensure_ascii=False))
except Exception as e:
    print(f"API Error: {e}")
