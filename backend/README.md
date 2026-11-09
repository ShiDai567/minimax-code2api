# 后端开发状态

Python 3.12+ Flask 服务。上游适配根据公开 CLI 和参考网关实现，但尚未使用真实凭证验证，不能视为生产就绪。前端仍然使用 mock 数据，未与本服务联调。

已实现：区域隔离的账号、分组和 API Key 管理；账号凭证加密；基于上游 `count_tokens` 的账号验证；Anthropic Messages 及 SSE 透传；OpenAI Chat/Responses 的纯文本非流式转换；签到及独立 worker 处理的批量和定时任务；持久化日志和可选的上游快照、模型发现适配器。

未实现：OpenAI 流式、工具调用和多模态转换；已验证的默认模型发现/余额上游；积分到账对账及真实使用扣费；前端联调；生产级身份/RBAC、速率限制和运维系统。模型与额度适配器默认关闭，不会伪造模型列表或余额。

本地启动见 [部署说明](../docs/deployment.md)，API 及数据语义见 [API 文档](../docs/api.md)。签到奖励为上游报告值，不代表积分到账。网络失败或 worker 崩溃可能导致结果未知，不能盲目重试；具体恢复方式见 API 文档。

```sh
python -m pytest -q
python -m compileall -q app tests migrations
```
