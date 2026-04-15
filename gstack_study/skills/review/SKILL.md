# review — 多专家代码审查

> 来源：gstack-main/review/（精简移植）
> 核心：6个专家角色，JSONL 输出格式，分工审查

## 触发条件

```
用户说"review"、"代码审查"、"检查diff"、"pre-landing review"
→ 执行这个 skill
```

---

## 输出格式（JSONL，每行一个发现）

```json
{"severity":"CRITICAL|INFORMATIONAL","confidence":0.9,"path":"file","line":47,
 "category":"security","summary":"...","fix":"..."}
```
- 无发现：输出 `NO FINDINGS`
- `confidence`：置信度 0.0-1.0
- `severity`：
  - CRITICAL = 必须修复才能合并
  - INFORMATIONAL = 建议改进，但不阻塞

---

## 6个专家角色

### 1. security（安全）

**触发：** 认证代码存在 OR diff>100行含后端

**关注点：**
- SQL注入、命令注入
- Auth/Authz绕过
- XSS、CSRF、SSRF
- 硬编码密钥/Token
- 反序列化漏洞

```
{"severity":"CRITICAL|INFORMATIONAL","confidence":N,"path":"file","line":N,
 "category":"security","summary":"...","fix":"...","specialist":"security"}
```

### 2. testing（测试）

**触发：** 始终开启

**关注点：**
- 缺失负向路径测试（错误分支、边界值）
- 测试隔离违规（共享状态、顺序依赖）
- Flaky测试模式（时间依赖、随机数据无seed）
- 缺失 Auth 拒绝测试

```
{"severity":"CRITICAL|INFORMATIONAL","confidence":N,"path":"file","line":N,
 "category":"testing","summary":"...","fix":"...","specialist":"testing"}
```

### 3. api-contract（API契约）

**触发：** 有API变更

**关注点：**
- 破坏性变更（删除字段、改变类型）
- 版本策略不一致
- 错误响应格式不统一
- 文档漂移（README vs 实际行为）
- 速率限制缺失

```
{"severity":"CRITICAL|INFORMATIONAL","confidence":N,"path":"file","line":N,
 "category":"api-contract","summary":"...","fix":"...","specialist":"api-contract"}
```

### 4. data-migration（数据迁移）

**触发：** 有数据库迁移

**关注点：**
- 不可逆迁移（无回滚方案）
- 数据丢失风险（drop列、类型截断）
- 大表ALTER锁（无CONCURRENTLY）
- 缺少回填脚本
- 迁移与应用代码部署顺序

```
{"severity":"CRITICAL|INFORMATIONAL","confidence":N,"path":"file","line":N,
 "category":"data-migration","summary":"...","fix":"...","specialist":"data-migration"}
```

### 5. maintainability（可维护性）

**触发：** 始终开启

**关注点：**
- 死代码/未使用导入
- 魔法数字（应命名常量）
- 陈旧注释/TODO指向已完成工作
- DRY违规（3+行重复代码）
- 模块边界违规（直接访问内部实现）

```
{"severity":"INFORMATIONAL","confidence":N,"path":"file","line":N,
 "category":"maintainability","summary":"...","fix":"...","specialist":"maintainability"}
```

### 6. red-team（红队）

**触发：** diff>200行 OR security专家发现CRITICAL

**运行顺序：** 在其他专家之后

**方法：** 对抗性分析，不是 checklist

```
{"severity":"CRITICAL|INFORMATIONAL","confidence":N,"path":"file","line":N,
 "category":"red-team","summary":"...","fix":"...","specialist":"red-team"}
```

**攻击路径：**

1. **攻击 Happy Path**
   - 10倍负载会发生什么？
   - 两个请求同时命中同一资源？
   - 数据库慢（>5s）会发生什么？
   - 外部服务返回垃圾数据？

2. **找静默失败**
   - catch-all 吞异常（只打日志）
   - 部分完成的操作（5个处理了3个然后崩溃）
   - 失败时留下不一致状态
   - 后台任务失败无人警报

3. **利用信任假设**
   - 前端验证但后端不验证
   - 内部API不验证认证（"只有我们的代码调用"）
   - 假设配置值存在但不验证
   - 路径/URL从用户输入构造未净化

4. **打破边界**
   - 最大输入会发生什么？
   - 零项、空字符串、null？
   - 首次运行（无现有数据）？
   - 用户100ms内点两次按钮？

5. **找其他专家遗漏的**
   - 跨类别问题（性能问题也是安全问题）
   - 集成边界问题（两个系统交汇处）
   - 特定部署配置下才暴露的问题

---

## 审查结果汇总

```
| 专家 | CRITICAL | INFORMATIONAL |
| security    | 2        | 3             |
| testing     | 0        | 5             |
| api-contract| 0        | 1             |
| red-team    | 1        | 2             |

VERDICT: BLOCK（需修复2个CRITICAL）/ MERGE（可合并）
```

---

## 自改进（完成前必须做）

反思：
- 哪些命令意外失败？
- 是否走了弯路需要回退？
- 是否发现项目特定的坑？

如有发现 → 记录到 evolver
