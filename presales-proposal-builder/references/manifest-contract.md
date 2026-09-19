# proposal_manifest.json 约定

对预计超过 4 页或涉及多个来源的正式方案建立内部任务清单，用于在写作前锁定方向和边界。该文件只存放在工作区，不得复制到客户输出目录或投标提交包。

## 最小示例

```json
{
  "schema_version": "1.1",
  "status": "ready",
  "project_name": "某集团档案数据治理项目",
  "proposal_type": "decision-report",
  "audience": ["集团分管领导", "档案部门负责人"],
  "purpose": "立项决策",
  "carrier": "docx",
  "source_mode": "summary-first",
  "requirements_provided": true,
  "sources": [
    {
      "id": "S1",
      "type": "project-summary",
      "location": "summaries/project.md",
      "usage": "客户现状和需求"
    }
  ],
  "confirmed_facts": ["现有档案分散在多个系统"],
  "product_mapping": [
    {
      "requirement": "对归档数据进行质量检测",
      "amber_product": "四性检测",
      "verified_capability": "对归档数据执行四性检测并记录结果",
      "fit": "standard",
      "writing_treatment": "纳入电子文件归档处理链"
    }
  ],
  "assumptions": ["本期仅处理非密数据"],
  "open_questions": [],
  "business_outcomes": ["形成统一、可追溯的档案数据利用入口"],
  "exclusions": ["不包含第三方系统改造费用"],
  "sections": [
    {
      "id": "1",
      "title": "建设背景与必要性",
      "decision_question": "为什么现在必须建设"
    }
  ],
  "claim_policy": "conservative"
}
```

## 字段规则

| 字段 | 规则 |
|---|---|
| `schema_version` | 固定为 `1.1` |
| `status` | `draft` 或 `ready` |
| `project_name` | 非空字符串 |
| `proposal_type` | `decision-report`、`marketing-solution`、`construction-plan`、`short-brief`、`revision` |
| `audience` | 至少一个明确角色 |
| `purpose` | 说明读者需要作出的决定或下一步动作 |
| `carrier` | `content`、`markdown`、`docx`、`pptx-manuscript` |
| `source_mode` | `summary-first`、`provided-extract`、`user-authorized-original`、`mixed` |
| `requirements_provided` | 布尔值；用户是否提供了明确需求内容 |
| `sources` | 每项包含 `id`、`type`、`location`、`usage` |
| `confirmed_facts` | 已有来源支撑的客户或项目事实 |
| `product_mapping` | 用户提供需求时，`draft` 状态可暂空并告警，`ready` 状态必须填写；每项包含 `requirement`、`amber_product`、`verified_capability`、`fit`、`writing_treatment` |
| `assumptions` | 为推进工作作出的可见假设 |
| `open_questions` | 尚待确认且可能影响范围的事项 |
| `business_outcomes` | 用业务结果描述，不写系统模块 |
| `exclusions` | 本期不包含项、第三方责任或条件 |
| `sections` | 每项包含 `id`、`title`、`decision_question` |
| `claim_policy` | 固定为 `conservative` |

`ready` 状态必须具备来源、事实、业务结果、范围排除和章节计划。若仍有会实质改变技术路线、报价或责任边界的问题，不应标为 `ready`。

`fit` 仅允许 `standard`、`extension`、`gap`、`third-party`。如果 `requirements_provided` 为 `true`，`draft` 状态允许 `product_mapping` 暂空但必须报告告警；进入 `ready` 状态前必须补齐，否则验证应阻断。该映射用于内部能力核验，不直接复制到客户成稿。
