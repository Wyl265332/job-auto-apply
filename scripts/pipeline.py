# -*- coding: utf-8 -*-
"""job-auto-apply 数据处理管道（不含浏览器操作）

三个子命令：
    python pipeline.py filter --config config.json --raw jobs_raw.json --out todo.json
    python pipeline.py report --results apply_results.json --jd jd_raw.json --round 2026-10-14 --platform iguopin
    python pipeline.py gate   --config config.json --name "岗位名" --jd "JD正文"

浏览器交互由 agent 用 chrome-devtools 工具完成，本脚本只做纯数据处理。
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
TOTAL_FILE = "投递汇总报告.md"
KW_FILE = "已查看岗位JD关键词总结.md"
MARKER = "<!-- AUTO-GENERATED BELOW -->"

# 精选能力词表：按需求替换。统计的是「多少条 JD 提到了它」，不是出现次数。
ABILITY = {
    "内容生产": ["文案", "推文", "公众号", "稿件", "撰写", "编辑", "选题"],
    "新媒体": ["新媒体", "短视频", "抖音", "小红书", "直播", "运营策划"],
    "活动执行": ["活动", "策划", "执行", "落地", "会务", "组织"],
    "数据与复盘": ["数据", "复盘", "转化", "指标", "分析", "报表"],
    "办公与协同": ["办公软件", "Excel", "PPT", "Word", "公文", "档案"],
    "沟通协调": ["沟通", "协调", "对接", "服务", "责任心", "抗压"],
}

HARD_CONDS = {
    "学历": ["本科", "硕士", "大专", "不限"],
    "专业": ["专业不限", "汉语言", "中文", "新闻传播", "管理类", "计算机"],
    "薪资": [r"\d+[~-]\d+K", r"\d+[~-]\d+元", r"月薪\s*\d+"],
    "优先项": ["优先", "加分", "有经验者", "党员", "学生干部"],
}


def load_cfg(path=None):
    for p in [path, os.path.join(os.getcwd(), "config.json"),
              os.path.join(SKILL_ROOT, "config.json"),
              os.path.join(SKILL_ROOT, "config.example.json")]:
        if p and os.path.exists(p):
            return json.load(open(p, encoding="utf-8"))
    raise SystemExit("找不到 config.json：请先从 config.example.json 复制一份到工作目录")


def load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


# ---------------- JD 门禁 ----------------

def jd_gate(name, jd, cfg):
    """返回 (放行, 命中标签, 说明)。

    注意：一定要把岗位名一起判——届别词经常只出现在标题里。
    """
    g = cfg["gate"]
    text = (name or "") + " " + (jd or "")
    for p in g.get("neg_regex", []):
        m = re.search(p, text)
        if m:
            return False, "", "JD要求工作经验:" + m.group(0)
    hits = [h for h in g.get("must_hit_any", []) if h in text]
    if not hits:
        return False, "", "JD未标明届别/应届/校招"
    return True, "+".join(hits[:3]), ""


def decide_resume(name, jd, cfg):
    """按 JD 信号词命中数选简历；全 0 取 default。禁止跨方向混投。"""
    r = cfg["resumes"]
    best, best_score, fallback = None, 0, r.get("default", "")
    for opt in r.get("options", []):
        jd_hit = sum(1 for k in opt.get("jd_signal", []) if k in (jd or ""))
        ti_hit = sum(1 for k in opt.get("title_signal", []) if k in (name or ""))
        score = jd_hit * 2 + ti_hit
        if score > best_score:
            best, best_score = opt["name"], score
    return best or fallback, best_score


# ---------------- 过滤去重 ----------------

def reject(job, cfg, positive):
    """列表级粗筛，返回拒绝原因；通过返回空串。"""
    f = cfg["filters"]
    name = job.get("name") or ""
    comp = job.get("company") or ""
    blob = "|".join(job.get("tags", []) or []) + "|" + (job.get("edu") or "")

    if not job.get("pk"):
        return "无主键"
    if positive and not any(k in name for k in positive):
        return "方向不对口"
    for k in cfg["keywords"].get("exact_blacklist_title", []):
        if k in name:
            return "精确黑名单:%s" % k
    for k in f.get("exclude_title_manage", []):
        if k in name:
            return "管理岗:%s" % k
    for k in f.get("industry_ban_words", []):
        if k in name:
            return "工业岗误伤:%s" % k
    for k in f.get("company_blacklist", []):
        if k and k in comp:
            return "黑名单集团:%s" % k
    for k in f.get("education_ban", []):
        if k in blob:
            return "学历不符:%s" % k
    if f.get("require_campus"):
        rec = job.get("rec") or ""
        wt = job.get("workType") or ""
        if rec and "校园" not in rec:
            return "非校园招聘:%s" % rec
        if wt and wt != "校园":
            return "非校招:%s" % wt
    ap = job.get("applied")
    ok_val = cfg["platform"].get("iguopin", {}).get("applied_ok_value", 2)
    if ap is not None and ap != ok_val:
        return "平台标记已投/不可用"
    return ""


def dedup(rows):
    """主键优先 + (name, company) 兜底。"""
    out, seen_pk, seen_nc = [], set(), set()
    for j in rows:
        pk = j.get("pk") or ""
        nc = (j.get("name"), j.get("company"))
        if pk:
            if pk in seen_pk:
                continue
            seen_pk.add(pk)
        if nc in seen_nc:
            continue
        seen_nc.add(nc)
        out.append(j)
    return out


# ---------------- 报告 ----------------

def dedup_success_first(records, key="pk"):
    order = {"ok": 0, "unknown": 1, "skip": 2, "fail": 3, "error": 4, "captcha": 5}
    best = OrderedDict()
    for r in records:
        k = r.get(key)
        if not k:
            continue
        if k not in best or order.get(r.get("result"), 9) < order.get(best[k].get("result"), 9):
            best[k] = r
    return list(best.values())


def round_report(records, date, platform):
    ok = [r for r in records if r.get("result") == "ok"]
    cnt = Counter(r.get("result") for r in records)
    reasons = Counter((r.get("note") or "").split(":")[0] for r in records
                      if r.get("result") != "ok")
    L = ["# %s 投递汇总（%s · 本轮）" % (date, platform),
         "",
         "- 处理 %d 条，成功 %d 条，成功率 %.1f%%" % (
             len(records), len(ok), 100.0 * len(ok) / max(1, len(records))),
         "- 结果分布：" + " / ".join("%s %d" % (k, v) for k, v in cnt.most_common()),
         "", "## 成功明细", "",
         "| # | 岗位 | 公司 | 城市 | 薪资 | 时间 |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(ok, 1):
        L.append("| %d | %s | %s | %s | %s | %s |" % (
            i, (r.get("name") or "")[:24], (r.get("company") or "")[:20],
            r.get("city") or r.get("dist") or "", r.get("salary") or "", r.get("ts") or ""))
    L += ["", "## 未投递原因分布", "", "| 原因 | 条数 |", "|---|---|"]
    for k, v in reasons.most_common(20):
        L.append("| %s | %d |" % (k, v))
    L.append("")
    return "\n".join(L)


def update_total(date, platform, records, path=TOTAL_FILE):
    """总报告：按 marker 截断旧内容后追加新批次，保证幂等。"""
    ok = len([r for r in records if r.get("result") == "ok"])
    try:
        txt = open(path, encoding="utf-8").read()
    except Exception:
        txt = "# 投递汇总报告\n\n%s\n" % MARKER
    if MARKER not in txt:
        txt = txt.rstrip() + "\n\n%s\n" % MARKER
    head = txt.split(MARKER)[0].rstrip() + "\n\n%s\n\n" % MARKER

    rows = {b[0] + b[1]: b for b in re.findall(
        r"^\| (20\d\d-\d\d-\d\d) \| (\S+) \| (\d+) \| (\d+) \|", txt, re.M)}
    rows[date + platform] = (date, platform, str(len(records)), str(ok))

    L = [head.rstrip(), "", "更新时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"), "",
         "## 批次汇总", "", "| 日期 | 平台 | 处理 | 成功 |", "|---|---|---|---|"]
    for k in sorted(rows):
        d, pf, n, s = rows[k]
        L.append("| %s | %s | %s | %s |" % (d, pf, n, s))
    L.append("| **合计** | — | **%d** | **%d** |" % (
        sum(int(r[2]) for r in rows.values()), sum(int(r[3]) for r in rows.values())))
    L += ["", "<!-- 历史成功明细由 pipeline.py 逐轮追加 -->", ""]
    open(path, "w", encoding="utf-8").write("\n".join(L))
    return sum(int(r[2]) for r in rows.values()), sum(int(r[3]) for r in rows.values())


def keyword_summary(jd_records, path=KW_FILE):
    jds = [r.get("jd") or "" for r in jd_records if r.get("jd")]
    n = len(jds)
    L = ["# 已查看岗位 JD 关键词总结", "",
         "样本：%d 条 JD（更新于 %s）" % (n, time.strftime("%Y-%m-%d %H:%M")), "",
         "## 一、能力词覆盖率（按 JD 条数）", "",
         "| 能力簇 | 提到该簇的 JD 数 | 覆盖率 | 高频词 |", "|---|---|---|---|"]
    flat = Counter()
    for cluster, words in ABILITY.items():
        hit_n, per = 0, Counter()
        for t in jds:
            found = [w for w in words if w in t]
            if found:
                hit_n += 1
                per.update(found)
        flat.update(per)
        L.append("| %s | %d | %.0f%% | %s |" % (
            cluster, hit_n, 100.0 * hit_n / max(1, n),
            "、".join(w for w, _ in per.most_common(4))))
    L += ["", "## 二、单关键词排行（Top 25）", "", "| 词 | JD 条数 |", "|---|---|"]
    for w, c in flat.most_common(25):
        L.append("| %s | %d |" % (w, c))
    L += ["", "## 三、硬性条件", "", "| 维度 | 命中情况 |", "|---|---|"]
    for dim, pats in HARD_CONDS.items():
        per = Counter()
        for t in jds:
            for p in pats:
                for m in re.findall(p, t):
                    per[str(m)] += 1
        L.append("| %s | %s |" % (dim, "、".join("%s(%d)" % (k, v) for k, v in per.most_common(6)) or "—"))
    L += ["", "## 四、可对标进简历的关键词", "",
          "- 覆盖率 ≥50% 的能力簇，按 JD 原话写进简历的项目描述里（不要编造经历）。",
          "- 排行前 10 的动词/名词，优先替换简历里的同义弱词。", "",
          "## 五、后续投递建议", "",
          "- 覆盖率低但薪资高的方向：说明是稀缺能力，可定向补一段经历再投。",
          "- 连续被「集团上限」拦截的集团，整组加入黑名单，不再消耗配额。", ""]
    open(path, "w", encoding="utf-8").write("\n".join(L))
    return n


# ---------------- CLI ----------------

def main():
    ap = argparse.ArgumentParser(description="job-auto-apply 数据处理管道")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("filter", help="过滤去重，生成待投清单")
    f.add_argument("--config", default=None)
    f.add_argument("--raw", default="jobs_raw.json")
    f.add_argument("--out", default="todo.json")

    r = sub.add_parser("report", help="生成三份报告")
    r.add_argument("--results", default="apply_results.json")
    r.add_argument("--jd", default="jd_raw.json")
    r.add_argument("--round", default=time.strftime("%Y-%m-%d"))
    r.add_argument("--platform", default="iguopin")

    g = sub.add_parser("gate", help="对单条岗位做 JD 门禁判定")
    g.add_argument("--config", default=None)
    g.add_argument("--name", default="")
    g.add_argument("--jd", default="")

    a = ap.parse_args()
    cfg = load_cfg(getattr(a, "config", None))

    if a.cmd == "filter":
        rows = load(a.raw, [])
        uniq = dedup(rows)
        positive = [k for grp in cfg["keywords"].get("groups", [])
                    for k in grp.get("positive_title", [])]
        todo, reasons = [], Counter()
        for j in uniq:
            why = reject(j, cfg, positive)
            if why:
                reasons[why.split(":")[0]] += 1
            else:
                todo.append(j)
        json.dump(todo, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("抓取 %d -> 去重 %d -> 待投 %d" % (len(rows), len(uniq), len(todo)))
        for k, v in reasons.most_common():
            print("  排除 %s: %d" % (k, v))

    elif a.cmd == "report":
        records = dedup_success_first(load(a.results, []))
        if not records:
            print("没有结果记录，跳过")
            return
        fn = "投递汇总-%s-%s.md" % (a.round, a.platform)
        open(fn, "w", encoding="utf-8").write(round_report(records, a.round, a.platform))
        tot_n, tot_ok = update_total(a.round, a.platform, records)
        n = keyword_summary(load(a.jd, []))
        print("本轮报告 -> %s；总报告累计 %d 条 / 成功 %d；JD 关键词样本 %d 条" % (fn, tot_n, tot_ok, n))

    elif a.cmd == "gate":
        ok, tag, why = jd_gate(a.name, a.jd, cfg)
        resume, score = decide_resume(a.name, a.jd, cfg)
        print(json.dumps({"pass": ok, "tag": tag, "reason": why,
                          "resume": resume, "score": score}, ensure_ascii=False))


if __name__ == "__main__":
    main()
