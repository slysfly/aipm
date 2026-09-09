#!/bin/bash
# AIPM自动化测试脚本（PMI版本）

LOG_FILE="/var/log/aipm_auto_test.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
PASS=0
FAIL=0

echo "[$TIMESTAMP] 开始自动化测试..." >> $LOG_FILE

# 测试1: 服务状态检查
if systemctl is-active --quiet ai-pm; then
    echo "[PASS] 服务运行正常" >> $LOG_FILE
    ((PASS++))
else
    echo "[FAIL] 服务未运行" >> $LOG_FILE
    ((FAIL++))
fi

# 测试2: API响应时间检查
START=$(date +%s%N)
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/v1/pmbok/agents > /tmp/api_test.tmp
END=$(date +%s%N)
ELAPSED=$(( (END - START) / 1000000 ))
HTTP_CODE=$(cat /tmp/api_test.tmp)

if [ "$HTTP_CODE" = "200" ] && [ $ELAPSED -lt 5000 ]; then
    echo "[PASS] API响应正常 (${ELAPSED}ms)" >> $LOG_FILE
    ((PASS++))
else
    echo "[FAIL] API响应异常 (HTTP:$HTTP_CODE, Time:${ELAPSED}ms)" >> $LOG_FILE
    ((FAIL++))
fi

# 测试3: 数据完整性检查
AGENT_COUNT=$(curl -s http://127.0.0.1:8000/api/v1/pmbok/stats | python3 -c 'import sys,json; print(json.load(sys.stdin)["agents_total"])' 2>/dev/null || echo '0')
if [ "$AGENT_COUNT" = "61" ]; then
    echo "[PASS] Agent数据完整 ($AGENT_COUNT个)" >> $LOG_FILE
    ((PASS++))
else
    echo "[FAIL] Agent数据异常 ($AGENT_COUNT个)" >> $LOG_FILE
    ((FAIL++))
fi

# 测试4: 内存使用检查
MEM_USAGE=$(free | awk '/Mem/ {printf "%d", $3/$2 * 100}')
if [ $MEM_USAGE -lt 80 ]; then
    echo "[PASS] 内存使用正常 (${MEM_USAGE}%)" >> $LOG_FILE
    ((PASS++))
else
    echo "[FAIL] 内存使用过高 (${MEM_USAGE}%)" >> $LOG_FILE
    ((FAIL++))
fi

echo "[$TIMESTAMP] 测试结果: $PASS通过, $FAIL失败" >> $LOG_FILE
echo "[$TIMESTAMP] 测试结果: $PASS通过, $FAIL失败"
