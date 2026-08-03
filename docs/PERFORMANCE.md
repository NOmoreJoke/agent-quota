# 性能与资源策略

## 当前实现边界

- 默认仅手动、按需刷新；无常驻 SchedulerHost、Renderer 定时器或 loopback listener。
- 无活跃账户时不会触发 Provider 网络查询。
- 应用包和 DMG 构建实行静态大小门禁；不以该门禁替代真实空闲功耗测试。
- Low Power Mode、thermal signal、后台合并调度、熔断器尚未实现，不声称已上线。

## 后台优化策略

| 项目 | 当前 | 启用自动刷新前的强制策略 |
|---|---|---|
| 调度 | manual/on-demand | SchedulerHost 单一进程；Renderer 禁止 timer |
| 合并 | 不适用 | 同 Provider/主体/能力请求合并；单次并发 `1` |
| 周期 | 不适用 | 最短 15 分钟 + 0–120 秒确定性 jitter；失败指数退避 |
| 电源 | 不适用 | Low Power Mode 暂停；恢复后不补发历史轮次 |
| 温控 | 不适用 | thermal serious/critical 暂停；nominal 后单次重算 |
| 生命周期 | 无常驻后台 | 仅账户存在且用户显式开启时注册；退出即释放 |
| 网络 | 用户手动触发 | offline 不重试；429/5xx 熔断；缓存命中不联网 |
| QoS | 前台按需 | 后台 `utility`；禁止 busy loop、轮询文件或 loopback listener |

自动刷新只有在上述策略具备状态机、错误注入、wakeups/网络计数与 10 分钟空闲测量
证据后才可默认开放；否则产品状态必须保持 manual/on-demand。

## Apple Silicon 兼容目标

目标为 `aarch64-apple-darwin`、macOS 13.0 及以上；所有 Apple Silicon Mac 共用
同一 arm64 产物，不按芯片代际或 Pro/Max/Ultra 型号特判。该声明是编译目标兼容范围，不代表所有芯片型号均已实机验证；
Intel/universal、Developer ID、公证与干净 VM 不在当前证据范围。

## 可复现门禁

```bash
uv run python tools/audit_package_size.py --root "artifacts/iteration-4/Agent Quota.app" --max-mib 40
```

构建脚本同时要求 DMG 不超过 20 MiB。真实资源验收仍需在目标 Mac 上记录 10 分钟
空闲 CPU、RSS、wakeups 与网络尝试次数；当前不提供未经测量的数值。
