# 智联招聘（zhaopin.com）

## 搜索页（免登录可抓）

URL：`https://www.zhaopin.com/jobs?kw=<关键词>&el=4&et=5&p=<页>`

| 参数 | 含义 |
|---|---|
| `kw` | 关键词 |
| `el=4` | 学历：本科 |
| `et=5` | 工作性质：校招 |
| `p=N` | 分页（智联翻页直接换 URL，不用点按钮） |

卡片：`div.job-card:not(.job-card--active)`

**突破口**：卡片 Vue 实例 `c.__vue__.$props.job` 里有完整 job 对象，含：

- `positionURL` / `positionUrl` —— **详情直链**
- `jobDescription` —— JD 正文（列表页就能拿到）
- `jobId`（number）、`workType`（「校园」= 校招）、`education`、`workingExp`、
  `salary60`、`workCity`、`cityDistrict`、`industryName`、`companySize`

抓取 JS 见 [js-snippets.md](js-snippets.md)「抓取-智联卡片」。实测 19/19 命中，免登录。

## 详情页

免登录也能打开，但 **JD 会被截断**，正文末尾是「登录查看完整内容」（实测只切出 429 字）。
**门禁判定必须先登录**，否则会漏掉 JD 里才有的届别/校招关键词。

投递流程（登录后）：

```
详情直链 → 读 JD → 门禁 → 点「立即投递」→ 弹窗 .a-modal 选简历 → 「投递简历」
        → 按钮变「继续沟通 / 已投递」即成功
```

## JD 门禁（智联尤其重要）

- **平台筛选标签不可信**，必须打开 JD 核对
- 放行词：目标届别 / 应届生 / 应届 / 校招 / 校园招聘
- 拦截正则：`[1-9]\s*年以上[\s\S]{0,8}经验`、`要求...N年...经验`、`[1-9]-[1-9]年经验`
- **判定文本只取 JD 正文**。智联导航栏自带「校招」频道入口，用页面头部会 100% 误命中
- JD 正文边界：从「职位描述 / 岗位职责 / 职位职责 / 任职要求」中最早出现者起，
  到「工作地点 / 公司信息 / 工商信息 / 相似职位 / 以担保或任何理由 / 举报」中最早出现者止
- 只有往届届别、没有目标届别 → 明细标注「限届别」，不静默跳过也不硬投

## 后台已投记录

```
https://i.zhaopin.com/schedule?status=delivered
```

（不是 `/record`，会被重定向首页。）

- 每页 19~20 条
- **URL 的 page 参数无效**，必须点 `.ivu-page-next` 翻页，否则重复计数

## 易错点

1. **登录弹窗和投递弹窗共用 `.a-modal` 类**（登录弹窗实测是
   `.a-modal.a-job-apply-workflow-close`）。判定分支里必须先排除登录框，
   否则会误判成「需完善简历」而 skip 一堆正常岗位。
2. 未登录点「立即投递」只弹登录框，不会真投递——不要把"点得动"当成链路通了。
3. 列表页 `.job-opt` 默认 0 尺寸，bsk 下点击会报 element not visible
   （chrome-devtools 下拿 uid 点没这个问题）。
