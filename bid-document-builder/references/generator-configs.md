# 图示生成器配置契约

本目录中的图示脚本不包含客户、项目、产品、日期、合规能力或统计数字默认值。配置必须在项目工作目录中创建，完成来源核验后再传入脚本；不要为配置项目而修改 skill 源文件。

## `assets/lib.js` 文档配置

调用 `cover(config)` 时以下字符串全部必填：`documentTitle`、`copyLabel`、`projectName`、`projectCode`、`packageNo`、`bidderName`、`submissionDate`。`makeHeader(config)` 必填 `projectName`、`documentTitle`、`packageNo`。缺少任何字段都会抛出错误，不会填入示例项目。

## 架构图配置

`make_arch.py` 接收 UTF-8 JSON：

```json
{
  "title": "<已确认的架构图标题>",
  "layers": [
    {
      "label": "<层级名称>",
      "sublabel": "<可选副标题>",
      "rows": [["<已确认组件一>", "<已确认组件二>"]]
    }
  ],
  "pillars": [
    {"label": "<可选纵向体系>"}
  ]
}
```

`layers` 至少一项、最多十项；每层至少一行，每行最多八个组件。`pillars` 可省略，最多两项。脚本不推断缺失层级或能力。提交版命令：

```powershell
python .\scripts\make_arch.py --config <项目配置.json> --output <项目工作目录\arch.png> --mode submission
```

## 原型图配置

`make_proto.py` 的 `layout` 只能是 `dashboard`、`table`、`form` 或 `flow`。四种模式分别要求：

- `dashboard`：`metrics`，每项含 `label`，`value` 可省略并显示为“—”；
- `table`：`columns`，`rows` 可省略；每行单元格数必须与列数相同；
- `form`：`fields`，元素可为字段名，也可为 `{"label": "…", "value": "…"}`；
- `flow`：`nodes`，至少两个节点。

通用字段为 `title`、可选 `subtitle`、可选 `buttons`。最小配置示例：

```json
{
  "title": "<已确认的功能名称>",
  "layout": "table",
  "columns": ["<字段一>", "<字段二>"],
  "rows": []
}
```

所有模式都会永久显示“原型示意｜非真实产品截图”。只有用户明确要求内部演示稿时才可使用 `--mode internal`；该参数不会移除水印。

字体可用 `--font-regular` 与 `--font-bold` 显式指定。自动探测不到中文字体时脚本会失败，以防生成乱码或方框。
