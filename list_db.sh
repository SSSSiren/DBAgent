#!/bin/bash
TOKEN="$ONEDBA_ACCESS_TOKEN"
curl -s -H "accessToken: ${TOKEN}" "https://onedba.shizhuang-inc.com/api/external/v1/agent/instance/schema/user/list?queryType=select&instanceType=acs_rds&mainBody=shizhuang&envType=test&page=1&size=30"
