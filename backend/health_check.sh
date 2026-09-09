#!/bin/bash
# AIPM健康检查脚本（PMI版本）

LOG_FILE="/var/log/aipm_health_check.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# 检查服务状态
if systemctl is-active --quiet ai-pm; then
    STATUS="OK"
else
    STATUS="CRITICAL"
fi

# 检查内存使用（整数）
MEM_USAGE=$(free | awk '/Mem/ {printf "%d", $3/$2 * 100}')
MEM_THRESHOLD=80

# 检查磁盘使用
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
DISK_THRESHOLD=85

# 检查API响应
API_STATUS=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/v1/pmbok/agents 2>/dev/null || echo '000')

# 输出结果
echo "[$TIMESTAMP] Service: $STATUS, Memory: $MEM_USAGE%, Disk: $DISK_USAGE%, API: $API_STATUS" | tee -a $LOG_FILE

# 告警逻辑
if [ "$STATUS" = "CRITICAL" ] || [ "$MEM_USAGE" -gt "$MEM_THRESHOLD" ] || [ "$DISK_USAGE" -gt "$DISK_THRESHOLD" ] || [ "$API_STATUS" != "200" ]; then
    echo "[WARNING] Health check failed! Check immediately." | tee -a $LOG_FILE
fi
