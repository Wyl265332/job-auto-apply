---
name: job-auto-apply
description: |
  Batch-apply to jobs on Chinese recruiting sites: 国聘 iguopin.com, 智联招聘 zhaopin.com,
  实习僧 shixiseng.com, 前程无忧 51job.com. Trigger when the user says 帮我投递简历 /
  批量投递 / 海投 / 自动投简历 / 帮我投 XX 方向的岗位, or asks to scrape job lists and
  produce a 投递报告. Drives the browser via chrome-devtools (primary) or bsk (fallback),
  screens every JD against the user's resume profile before applying, and auto-saves
  JDs + logs into a dated folder tree.
---

# job-auto-apply

用户说一句「帮我投递简历」，你就按本文件走完：
**环境自检 → 抓岗位 → 简历驱动筛选 → 试投 3 条 → 放量 → 出报告。**

浏览器操作**由你（agent）用 chrome-devtools 工具逐步执行**（chrome-devtools MCP 没有 HTTP
调试端口，Python 脚本无法自驱动）。数据处理交给 `scripts/workflow.py`。
框架不含任何个人数据，身份与偏好全部走 `config.json` + `resume_profile.json`。

## 一、首次使用：检测 → 弹窗让用户选 → 一键安装

**每次用户第一次用这个 skill（或 `config.json` 不存在）时，必须走这段。**

### 步骤 1 · 体检

```bash
python <skill>/scripts/setup.py --check
```

同时你自己调一次 `list_pages` 确认 chrome-devtools 可用（脚本检测不了 MCP）。

### 步骤 2 · 弹选择（用 AskUserQuestion，不要自己替用户决定）

问题 1「用哪个驱动操控浏览器？」
- **chrome-devtools（推荐）** —— 定位稳、没有 daemon 烦恼；需要你在连接器面板启用
- **bsk（备用）** —— 用你日常那个已登录的浏览器，天然带登录态；需要装 CLI 和浏览器扩展
- **两个都装** —— 主用 chrome-devtools，它挂了自动切 bsk

问题 2「简历记录与 JD 存到哪？」
- 默认 `~/Documents/投递记录`（推荐）
- 当前工作目录下 `投递记录`
- 自定义路径

问题 3「接下来要投什么？」（一次性问完，别挤牙膏）
- 平台（国聘 / 智联 / 实习僧 / 51job，可多选）
- 方向关键词 5~10 个
- 简历有几份、在平台上叫什么名字（**一字不差**）
- 硬性条件：学历底线 / 是否只投校招 / 届别 / 城市 / 薪资下限 / 要避开的公司或岗位类型

### 步骤 3 · 一键安装

```bash
python <skill>/scripts/setup.py --driver <用户选的> --root <用户选的路径>
python <skill>/scripts/workflow.py init --root <路径>
```

`setup.py` 能自动做的会自己做（建目录、生成配置、检测/尝试装 bsk），
装不了的（MCP 启用、浏览器扩展）会**打印明确的人工步骤**——把这几步原样转给用户，
**不要假装装好了**。装完再跑一次 `workflow.py doctor` 确认全绿。

### 步骤 4 · 填两份配置（不填就没有防误投能力）

- `config.json` —— 关键词、黑名单、平台 URL、驱动
- `resume_profile.json` —— **简历画像**，防误投的核心。见
  [references/resume-screening.md](references/resume-screening.md)

填完引导用户校对一遍，特别是**简历名**和**届别**。

## 二、运行条件

| # | 条件 | 怎么验 |
|---|---|---|
| 1 | 驱动可用 | chrome-devtools：`list_pages` 有返回；bsk：`bsk status --json` |
| 2 | 目标站点**已登录** | 见下 |
| 3 | 至少一份在线简历已建好且信息完整 | 试投时弹窗里能选到 |
| 4 | `config.json` + `resume_profile.json` 已填 | `workflow.py doctor` 全绿 |

**登录态判定**（一次 evaluate 即可，JS 在 js-snippets 里）：

- 国聘：详情页正文 < 500 字 且 按钮有「微信登录 / 密码登录 / 短信验证码」
- 智联：出现 `.a-modal` 且文案含「欢迎来到智联招聘」
- 实习僧：出现 `.footer-login--is-show`（短信登录 / 密码登录 / 微博 / QQ）

**未登录就停下来让用户手动登录一次**，登录态会留在浏览器实例里。这是唯一必须人工的一步。
不要代填验证码、不要绕过登录。

## 三、平台能力（2026-10-14 实测）

| 平台 | 列表 | 详情 | 投递按钮 | 结论 |
|---|---|---|---|---|
| **实习僧** | ✅ 免登录 | ✅ 免登录 | ✅ **免登录可见**「投个简历」 | **首选**，链路最干净 |
| **国聘** | ✅ 免登录 | ❌ 整页登录墙 | 登录后 | 可用，需登录 |
| **智联** | ✅ 免登录 | ⚠️ 未登录会截断 | ✅ 可见（点开弹登录） | 可用，需登录 |
| 51job | ✅ 免登录 | ❌ **滑块验证** | — | **只能抓列表** |
| BOSS 直聘 | ❌ 被踢成 about:blank | — | — | **不可用** |
| 猎聘 | ❌ 被踢成 about:blank | — | — | **不可用** |

细节见 [platform-iguopin.md](references/platform-iguopin.md) /
[platform-zhilian.md](references/platform-zhilian.md) /
[platform-more.md](references/platform-more.md)。

## 四、操作流程

### 1 · 抓岗位

```
navigate_page   → 搜索页 URL
evaluate_script → 抓卡片 JS（js-snippets）
翻页（实习僧/51job 换 URL 参数；国聘点 .ant-pagination-next；智联换 p=）
```

把抓到的数组写成 json 文件，然后：

```bash
python <skill>/scripts/workflow.py ingest --raw raw.json --platform <平台>
```

去重后落 `投递记录/raw/raw-<日期>-<平台>.json`。**每条必须有主键**（`job_id` / `jobId` / `inn_xxx`），
没有主键的卡片直接丢——没有主键只能回列表按位置点，列表会漂移，必然成片失败。

### 2 · 简历驱动筛选（防误投的关键）

**每条岗位在投递前必须过一次 screen，不过不许投。**

```bash
echo '{"job":{...},"jd":"..."}' | python <skill>/scripts/workflow.py screen --platform <平台>
```

返回 `pass` / `score` / `resume` / `reasons`：

- `pass=false` → **不投**，把 reason 记进日志
- `pass=true` → 按返回的 `resume` 选简历

同时自动把 JD 存成两份：
`投递记录/jd/<日期>/<平台>/<pk>.json` 和 `<pk>.md`。

判定维度：否决词 → 校招/届别 → 工作经验负向 → 学历 → 专业 → 城市 → 薪资下限 → 能力词加分 → 选简历。
见 [resume-screening.md](references/resume-screening.md)。

### 3 · 试投 3 条（**在确认前停手**）

```
navigate_page   → 详情直链
evaluate_script → 切 JD + 门禁
workflow.py screen → 是否放行、用哪份简历
take_snapshot   → 找投递按钮 uid
click           → 打开弹窗
evaluate_script → 读弹窗结构
```

**停下**，向用户汇报：门禁结果、选哪份简历、弹窗里有什么按钮、以及「链路通了，是否放量？」。
**用户点头才继续。** 未登录时点按钮只弹登录框——别把这个当链路通了。

### 4 · 放量

用户确认后逐条闭环，每处理完一条立刻记日志（保证中断可续）：

```bash
echo '{"pk":"...","name":"...","result":"ok","note":"投递成功","resume":"简历A"}' \
  | python <skill>/scripts/workflow.py log --platform <平台>
```

- 每 20 条汇报一次进度
- 续跑前先读当天 jsonl，跳过已处理的 pk
- 结果取值：`ok` / `skip` / `fail` / `unknown` / `captcha` / `error`

### 5 · 出报告

```bash
python <skill>/scripts/workflow.py report --platform <平台>
```

产出三份：本轮明细、合并进 `投递汇总报告.md` 的总报告（幂等）、`已查看岗位JD关键词总结.md`。

## 五、目录结构（自动建）

```
投递记录/
├── jd/<日期>/<平台>/<pk>.json     岗位 + JD + 筛选结果
│              └─ <pk>.md        人能读的版本
├── logs/<日期>-<平台>.jsonl       逐条投递日志（可断点续跑）
│     投递汇总-<日期>-<平台>.md    本轮报告
├── raw/raw-<日期>-<平台>.json     抓取去重后的卡片
├── 投递汇总报告.md                 总报告（幂等累加）
└── 已查看岗位JD关键词总结.md
```

（`config.json` 与 `resume_profile.json` 放在**工作目录**，不在这里。）
默认位置 `~/Documents/投递记录`，`init` 时可改。

## 六、注意事项（红线）

1. **遇验证码 / 登录失效 / 页面结构异常 → 立即停止并告知用户。** 不重试、不绕过。
2. **不过 screen 就不许投。** 平台筛选标签不可信，JD 门禁必须走。
3. **失败立即跳下一条，不重试。** 同一条最多换一次简历兜底。
4. **频率控制**：每条之间 sleep 0.8~1.5 秒，不并发、不轰炸。
5. **不编造任何信息。** 简历选择只按 profile 规则；禁止跨方向混投。
6. **集团上限**：被「同一单位最多投 N 个职位」拦截的集团整组跳过并加黑名单。
7. **只有"真失败"才收藏**。专属模板、已达上限、此前已投一律不收藏。
8. **不碰凭据**：不导 cookie、不填密码、不做免登。登录只由用户手动完成。
9. **数字只来自落盘记录**，成功数按主键去重、成功优先。
10. **撞滑块 / about:blank 的平台直接判不可用**，换下一个，不要硬刚反爬。

## 七、脚本

| 文件 | 用途 |
|---|---|
| `scripts/workflow.py` | `init` 建目录 / `doctor` 体检 / `ingest` 收卡片去重 / `screen` 简历驱动筛选 / `log` 记日志 / `report` 出报告 |
| `scripts/setup.py` | 一键安装：选驱动 → 建目录 → 生成配置 → 打印人工步骤 |
| `scripts/pipeline.py` | 轻量管道（filter/report/gate），workflow 的补充 |
| `scripts/bskw.py` | bsk 驱动封装（备用路径） |

## 八、验收清单

- [ ] 首用走了「检测 → 弹窗选择 → 一键安装」，人工步骤已转达用户
- [ ] `workflow.py doctor` 全绿
- [ ] 登录态是**验过的**，不是靠"没报错"推断
- [ ] 每条都过了 `screen`，`pass=false` 的没投
- [ ] JD 已落 `jd/<日期>/<平台>/`，日志在 `logs/<日期>-<平台>.jsonl`
- [ ] 试投 3 条后向用户汇报并**等确认**才放量
- [ ] 成功率突然掉 → 先查登录态和按钮定位，别硬跑
