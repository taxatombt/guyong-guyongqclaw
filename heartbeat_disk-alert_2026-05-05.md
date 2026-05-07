# 磁盘告警 2026-05-05

## 磁盘严重恶化

| 盘符 | 剩余 | 百分比 | 趋势 |
|------|------|--------|------|
| C: | 12.7GB | 8.5% | ↓ (昨天14.4GB) |
| D: | 2.9GB | 0.2% | 危险 |
| E: | 4.2GB | 1.3% | ⚠️骤降 (3天前22.4GB!) |
| F: | 0.5GB | 0.1% | 危险 |

## E盘骤降排查（3天掉18GB）

- 迅雷下载 = **93.55GB**（最大项）
- 电脑容器 = ~9GB
- 近期新增目录：juhuo、temp_guhuo_files、free-claude-code、mattpocock-skills、openclaw、gitnexus、ml-intern、nodejs-v22、Hermes、qwenpaw

## 建议优先清理

1. **迅雷下载** — 93.55GB，已下载完的移走或删除
2. **电脑容器** — ~9GB，检查是否还在用
3. **temp_guhuo_files + temp_guhuo.tar.gz** — 临时文件可删
4. **C盘 Downloads** — 1.5GB可清
5. **C盘 Temp** — 768MB可清

## 其他发现

- LoL正在运行（League of Legends 955MB + LeagueClient 585MB）
- openclaw gateway service unit not found（但系统显示pid 10824运行中）
- MiniMax-M2.7 模型不支持错误
