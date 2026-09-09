#!/bin/bash
# AIPM数据库备份脚本（PMI版本）

BACKUP_DIR="/opt/aipm-install/backend/backups"
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
DB_FILE="/opt/aipm-install/backend/tw_ai_pms.db"
BACKUP_FILE="$BACKUP_DIR/tw_ai_pms.db.$TIMESTAMP.backup"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 执行备份
if cp $DB_FILE $BACKUP_FILE; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 数据库备份成功: $BACKUP_FILE" | tee -a /var/log/aipm_backup.log
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 数据库备份失败!" | tee -a /var/log/aipm_backup.log
    exit 1
fi

# 清理3天前的备份(保留3天)
find $BACKUP_DIR -name '*.backup' -mtime +3 -delete
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 已清理3天前的旧备份(保留3天)" >> /var/log/aipm_backup.log
