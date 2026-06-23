# Gateway 状态检查

**时间**: 2026-06-18 21:50 (Asia/Shanghai)

## 问题

后台命令执行失败（SIGKILL 信号终止），Gateway 服务未运行。

## 状态

- **Service**: Scheduled Task (missing)
- **Runtime**: stopped (ERROR: The system cannot find the file specified.)
- **Listening**: 127.0.0.1:12178
- **Connectivity probe**: ok
- **Capability**: admin-capable

## 结论

Gateway 服务未安装或已停止。计划任务服务缺失。

## 下一步

执行 `openclaw gateway start` 启动服务，或 `openclaw gateway install` 安装服务。
