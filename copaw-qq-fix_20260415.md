# CoPaw QQ Channel 配置修复

## 时间
2026-04-15 14:21-14:33 GMT+8

## 问题
CoPaw Desktop 不回复 QQ 消息

## 排查
1. 发现 config.json 中 QQ channel disabled → 改为 enabled + 填入凭证 → 不够
2. 发现 agent.json（workspace级配置）中 QQ 也是 disabled → 也要改
3. CoPaw 有**两层配置**：全局 config.json + workspace agent.json，只改一层不够

## 修复
- `C:\Users\yiseg\.copaw\config.json` → qq.enabled: true + app_id + client_secret
- `C:\Users\yiseg\.copaw\workspaces\default\agent.json` → channels.qq.enabled: true + app_id + client_secret
- 完全重启 CoPaw Desktop

## 关键经验
- **CoPaw 双层配置**：改 channel 配置时，config.json 和 agent.json 都要改
- **热加载不够**：AgentConfigWatcher 检测到变更但报 "channel 'qq' not found, skip"，必须完全重启
- **App ID 冲突**：QClaw 和 CoPaw 不能用同一个 App ID

## 结果
14:33 小谷确认 QQ channel 已通
