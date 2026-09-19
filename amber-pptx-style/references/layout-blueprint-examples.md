# 安铂 PPT 动态版式蓝图示例

本文件用于解决“知道原则但生成时仍回到固定模板”的问题。正式制作前，先把每页规划成类似下面的蓝图，再由当前 `Presentations` Skill 完成 PPTX 实现。

## 1. 蓝图字段

| 字段 | 必填 | 说明 |
|---|---|---|
| slide_id | 是 | 页码或稳定编号 |
| role | 是 | 页面真实任务，如 Opening Signal、Problem Diagnosis、Solution Architecture、Decision Page |
| core_message | 是 | 本页要让客户相信的一句话结论 |
| content_signals | 是 | 内容信号，如 阶段、层级、比较、数据、场景、政策映射、风险保障 |
| layout_family | 是 | 版式家族，如 诊断、架构、流程、矩阵、数据证据、故事板、决策建议 |
| layout_variant | 是 | 具体变体，不要只写“内容页” |
| visual_focus | 是 | 一眼看到的主视觉：大数字、架构、流程、矩阵、截图、证据链 |
| components | 是 | 页面构件：主图、侧栏、标签、SO WHAT、脚注、图例等 |
| density | 是 | low / medium / high |
| layout_reason | 是 | 为什么该内容适合这个版式 |
| avoid | 建议 | 本页禁止退回的低质表达 |

## 2. 一句话售前方案示例

主题：给某集团做档案数据治理与智能利用汇报。

```json
{
  "slides": [
    {
      "slide_id": 1,
      "role": "Opening Signal",
      "core_message": "档案建设正在从合规保管升级为集团数据资产运营能力",
      "content_signals": ["决策汇报", "战略升级", "强判断"],
      "layout_family": "单观点强调",
      "layout_variant": "C1 决策判断封面",
      "visual_focus": "大标题 + 橙色判断线 + 低密度深蓝识别区",
      "components": ["标题", "价值短句", "客户/日期", "品牌识别"],
      "density": "low",
      "layout_reason": "开场需要先建立管理判断，不适合放目录或功能模块",
      "avoid": ["默认目录", "产品功能清单", "三卡片封面"]
    },
    {
      "slide_id": 2,
      "role": "Executive Framing",
      "core_message": "当前矛盾不是缺少系统，而是数据、流程、利用场景没有贯通",
      "content_signals": ["现状问题", "矛盾分析", "管理风险"],
      "layout_family": "诊断",
      "layout_variant": "问题树 + 右侧证据块",
      "visual_focus": "三层问题归因图",
      "components": ["问题树", "证据块", "底部 SO WHAT"],
      "density": "medium",
      "layout_reason": "内容核心是因果诊断，应该呈现问题链路，而不是三张痛点卡片",
      "avoid": ["痛点三卡片", "纯 bullet"]
    },
    {
      "slide_id": 3,
      "role": "Solution Architecture",
      "core_message": "统一数据底座需要同时承接应用、能力、数据与安全标准体系",
      "content_signals": ["系统", "层级", "平台底座"],
      "layout_family": "架构分层",
      "layout_variant": "四层平台架构 + 侧栏说明",
      "visual_focus": "分层架构图",
      "components": ["应用层", "能力层", "数据层", "安全标准", "侧栏 SO WHAT"],
      "density": "high",
      "layout_reason": "内容是平台层级关系，必须用架构图表达支撑关系",
      "avoid": ["功能列表", "九宫格模块"]
    },
    {
      "slide_id": 4,
      "role": "Roadmap",
      "core_message": "项目可以按治理底座、业务协同、智能利用三阶段稳妥推进",
      "content_signals": ["阶段", "路径", "落地计划"],
      "layout_family": "流程路线",
      "layout_variant": "三阶段路线图 + 里程碑",
      "visual_focus": "横向路线图",
      "components": ["阶段节点", "交付物", "风险控制", "下一步动作"],
      "density": "medium",
      "layout_reason": "内容重点是推进顺序和可落地性，路线图比卡片更合适",
      "avoid": ["建设内容清单", "平均三卡片"]
    }
  ]
}
```

## 3. 产品演示型示例

产品演示不要从目录开始，优先从场景进入。

```json
{
  "slides": [
    {
      "slide_id": 1,
      "role": "Scenario Storyboard",
      "core_message": "一次档案利用申请可以被系统自动串起检索、授权、借阅和留痕",
      "content_signals": ["客户场景", "业务动作", "演示路径"],
      "layout_family": "场景故事板",
      "layout_variant": "角色-动作-系统三幕式",
      "visual_focus": "三幕业务场景链路",
      "components": ["角色标签", "动作节点", "系统响应", "结果反馈"],
      "density": "medium",
      "layout_reason": "演示型 PPT 先让客户看到业务闭环，比先放产品目录更有效",
      "avoid": ["功能菜单截图堆叠", "默认封面"]
    },
    {
      "slide_id": 2,
      "role": "Capability Detail",
      "core_message": "智能检索能力由语义理解、权限过滤、结果排序和利用留痕共同支撑",
      "content_signals": ["能力组成", "系统模块", "流程"],
      "layout_family": "能力地图",
      "layout_variant": "中心能力 + 四周支撑模块",
      "visual_focus": "中心辐射能力图",
      "components": ["中心能力", "四个支撑模块", "输入输出", "SO WHAT"],
      "density": "high",
      "layout_reason": "内容是多个能力围绕一个核心服务，适合中心辐射而不是四卡片",
      "avoid": ["四个等高卡片", "纯截图"]
    }
  ]
}
```

## 4. 投标/评分响应型示例

投标演示必须让评分点和响应证据对齐，不要做成普通方案介绍。

```json
{
  "slides": [
    {
      "slide_id": 1,
      "role": "Evidence Page",
      "core_message": "本方案逐项响应评分要求，并以功能、案例和交付物形成可核验证据",
      "content_signals": ["评分点", "政策条款", "证据映射"],
      "layout_family": "映射表",
      "layout_variant": "评分点-响应-证据三列",
      "visual_focus": "评分响应映射表",
      "components": ["评分点", "响应策略", "证据材料", "风险提示"],
      "density": "high",
      "layout_reason": "内容核心是条款与证据的对应关系，必须用映射结构",
      "avoid": ["价值口号页", "普通目录页"]
    },
    {
      "slide_id": 2,
      "role": "Decision Page",
      "core_message": "推荐以低风险实施路径保障上线、验收和后续运营",
      "content_signals": ["决策", "风险控制", "下一步行动"],
      "layout_family": "决策建议",
      "layout_variant": "建议结论 + 风险控制 + 行动项",
      "visual_focus": "决策建议块",
      "components": ["建议结论", "三项理由", "风险控制", "下一步"],
      "density": "medium",
      "layout_reason": "结尾要帮助评审或领导判断方案可落地，不应默认谢谢页",
      "avoid": ["联系方式页", "空泛结束语"]
    }
  ]
}
```
