# -*- coding: utf-8 -*-
"""job-auto-apply 批量投递工作流（纯数据处理，不含浏览器操作）

浏览器交互由 agent 用 chrome-devtools（主）或 bsk（备）完成，本脚本负责：

    init     初始化工作目录 + 生成 config.json / resume_profile.json 模板
    doctor   检测依赖（驱动可用性、目录、配置），输出缺失项与安装指引
    ingest   收下 agent 抓到的卡片数组，去重后落 raw
    screen   简历驱动筛选：按 resume_profile 判定这条岗位该不该投、用哪份简历
    log      追加一条投递结果到当日 jsonl 日志
    report   生成三份报告（本轮 / 总报告 / JD 关键词总结）

典型链路：
    init → doctor → (agent 抓卡片) → ingest → screen → (agent 投递) → log → report
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)

DEFAULT_ROOT = os.path.join(os.path.expanduser("~"), "Documents", "投递记录")

# ---------------- 目录 ----------------


def cfg_path():
    return os.path.join(os.getcwd(), "config.json")


def profile_path():
    return os.path.join(os.getcwd(), "resume_profile.json")


def load_json(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def root_of(cfg=None):
    cfg = cfg or {}
    return cfg.get("output", {}).get("root") or DEFAULT_ROOT


def ensure(p):
    if not os.path.exists(p):
        os.makedirs(p)
    return p


def paths(root, date=None, platform=None):
    date = date or time.strftime("%Y-%m-%d")
    d = {"root": root, "jd": os.path.join(root, "jd", date),
         "log": ensure(os.path.join(root, "logs")),
         "raw": ensure(os.path.join(root, "raw"))}
    if platform:
        d["jd_platform"] = ensure(os.path.join(d["jd"], platform))
        d["log_file"] = os.path.join(d["log"], "%s-%s.jsonl" % (date, platform))
        d["todo"] = os.path.join(d["raw"], "todo-%s-%s.json" % (date, platform))
        d["raw_file"] = os.path.join(d["raw"], "raw-%s-%s.json" % (date, platform))
    return d


# ---------------- 简历驱动筛选（核心） ----------------

EDU_ORDER = {"不限": 0, "初中": 1, "高中": 2, "中专": 3, "中技": 3, "大专": 4,
             "本科": 5, "硕士": 6, "博士": 7}


def edu_level(text):
    """取文中出现过的**最高**学历档位。

    坑：不能按顺序取第一个匹配——「专业不限」里的「不限」会先命中，导致把本科岗判成学历不达标。
    """
    t = text or ""
    if re.search(r"学历\s*[:：]?\s*不限|不限学历|学历不限", t):
        return None
    vals = [v for k, v in EDU_ORDER.items() if k != "不限" and k in t]
    return max(vals) if vals else None


def screen(job, jd, prof, cfg=None):
    """简历驱动筛选。

    返回 dict：
      pass     是否放行
      score    匹配分（越高越该投）
      resume   建议用哪份简历
      hard     硬性条件逐项结果
      veto     命中否决词
      reasons  人话说明
    """
    cfg = cfg or {}
    hard = prof.get("hard", {})
    soft = prof.get("soft", {})
    rules = prof.get("apply_rules", cfg.get("gate", {}))

    name = job.get("name") or ""
    company = job.get("company") or ""
    city = job.get("city") or job.get("dist") or ""
    salary = job.get("salary") or ""
    text = name + " " + (jd or "")
    reasons, veto, score = [], [], 0
    ok = True

    # 1) 否决词（最先判，命中直接出局）
    for w in soft.get("veto", []):
        if w and w in text:
            veto.append(w)
    if veto:
        return {"pass": False, "score": 0, "resume": "", "hard": {},
                "veto": veto, "reasons": ["命中否决词：" + "、".join(veto[:5])]}

    # 2) 招聘类型 / 届别（校招场景）
    if rules.get("require_campus", True):
        campus = rules.get("campus_words", ["校招", "校园招聘", "应届", "应届生", "在校生"])
        hits = [w for w in campus if w in text]
        if not hits:
            ok = False
            reasons.append("未标明届别/应届/校招")
        else:
            score += 2
            reasons.append("命中：" + "+".join(hits[:3]))

    # 3) 工作经验负向
    for p in rules.get("neg_regex", []):
        m = re.search(p, text)
        if m:
            ok = False
            reasons.append("要求工作经验：" + m.group(0))
            break

    # 4) 学历
    ban_edu = hard.get("education_ban", [])
    hit_ban = [e for e in ban_edu if e in text]
    if hit_ban:
        ok = False
        reasons.append("学历不符：" + "/".join(hit_ban))
    lv = edu_level(text)
    need = EDU_ORDER.get(hard.get("education_min", "本科"), 5)
    if lv is not None and lv < need:
        ok = False
        reasons.append("学历低于门槛")

    # 5) 专业
    majors = hard.get("majors", [])
    any_ok = hard.get("major_any_ok", ["专业不限", "不限专业"])
    if majors:
        if any(k in text for k in any_ok):
            score += 1
        elif any(m in text for m in majors):
            score += 2
            reasons.append("专业对口")
        elif re.search(r"专业[:：]?\s*\S{2,}", jd or ""):
            # JD 写了专业要求但没命中自己的专业 → 不放行
            ok = False
            reasons.append("专业要求不匹配")

    # 6) 城市
    cities = hard.get("cities", [])
    if cities and city and not any(c in city for c in cities):
        ok = False
        reasons.append("城市不符：" + city)

    # 7) 薪资下限
    smin = hard.get("salary_min")
    if smin:
        nums = [int(x) for x in re.findall(r"(\d+)", salary.replace(",", ""))]
        if nums:
            top = max(nums)
            unit_k = "K" in salary.upper() or "k" in salary
            val = top * 1000 if (unit_k or top < 100) else top
            if val < smin:
                ok = False
                reasons.append("薪资低于下限：%s" % salary)

    # 8) 能力词加分（软匹配）
    for cluster, words in soft.get("ability", {}).items():
        hit = [w for w in words if w in (jd or "")]
        if hit:
            score += min(len(hit), 3)
            reasons.append("%s(%d)" % (cluster, len(hit)))
    for b in soft.get("bonus", []):
        if b in text:
            score += 1

    # 9) 选简历：按各简历的能力词命中数取最高
    best, best_score = prof.get("resume_default", ""), 0
    for r in prof.get("resumes", []):
        s = sum(1 for k in r.get("signals", []) if k in (jd or ""))
        if s > best_score:
            best, best_score = r["name"], s

    return {"pass": ok, "score": score, "resume": best or prof.get("resume_default", ""),
            "hard": {"edu_hit_ban": hit_ban, "city": city, "salary": salary},
            "veto": veto, "reasons": reasons}


# ---------------- 去重 ----------------

def dedup(rows):
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

def dedup_success_first(records):
    order = {"ok": 0, "unknown": 1, "skip": 2, "fail": 3, "error": 4, "captcha": 5}
    best = OrderedDict()
    for r in records:
        k = r.get("pk")
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
    L = ["# %s 投递汇总（%s · 本轮）" % (date, platform), "",
         "- 处理 %d 条，成功 %d 条，成功率 %.1f%%" % (
             len(records), len(ok), 100.0 * len(ok) / max(1, len(records))),
         "- 结果分布：" + " / ".join("%s %d" % (k, v) for k, v in cnt.most_common()),
         "", "## 成功明细", "",
         "| # | 岗位 | 公司 | 城市 | 薪资 | 简历 | 时间 |", "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(ok, 1):
        L.append("| %d | %s | %s | %s | %s | %s | %s |" % (
            i, (r.get("name") or "")[:24], (r.get("company") or "")[:20],
            r.get("city") or "", r.get("salary") or "", r.get("resume") or "", r.get("ts") or ""))
    L += ["", "## 未投递原因分布", "", "| 原因 | 条数 |", "|---|---|"]
    for k, v in reasons.most_common(20):
        L.append("| %s | %d |" % (k, v))
    return "\n".join(L) + "\n"


MARKER = "<!-- AUTO-GENERATED BELOW -->"


def update_total(date, platform, records, path):
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
    L += ["", "<!-- 历史明细由 workflow.py 逐轮追加 -->", ""]
    open(path, "w", encoding="utf-8").write("\n".join(L))
    return sum(int(r[2]) for r in rows.values()), sum(int(r[3]) for r in rows.values())


def keyword_summary(jd_dir, out_path):
    jds = []
    for dp, _, fns in os.walk(jd_dir):
        for fn in fns:
            if fn.endswith(".json"):
                try:
                    jds.append(json.load(open(os.path.join(dp, fn), encoding="utf-8")).get("jd") or "")
                except Exception:
                    pass
    jds = [x for x in jds if x]
    n = len(jds)
    ABILITY = {
        "内容生产": ["文案", "推文", "公众号", "稿件", "撰写", "编辑", "选题"],
        "新媒体": ["新媒体", "短视频", "抖音", "小红书", "直播", "运营策划"],
        "活动执行": ["活动", "策划", "执行", "落地", "会务", "组织"],
        "数据与复盘": ["数据", "复盘", "转化", "指标", "分析", "报表"],
        "办公与协同": ["办公软件", "Excel", "PPT", "Word", "公文", "档案"],
        "沟通协调": ["沟通", "协调", "对接", "服务", "责任心", "抗压"],
    }
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
    L += ["", "## 三、可对标进简历的关键词", "",
          "- 覆盖率 ≥50% 的能力簇，按 JD 原话写进项目描述里（不要编造经历）。",
          "- 排行前 10 的词替换简历里的同义弱词。", "",
          "## 四、后续投递建议", "",
          "- 覆盖率低但薪资高的方向：稀缺能力，可定向补经历再投。",
          "- 连续被「集团上限」拦截的集团，整组加黑名单。", ""]
    open(out_path, "w", encoding="utf-8").write("\n".join(L))
    return n


# ---------------- 子命令 ----------------

def cmd_init(a):
    root = a.root or DEFAULT_ROOT
    try:
        ensure(root)
    except Exception:
        root = os.path.join(os.getcwd(), "投递记录")
        ensure(root)
    if not os.path.exists(cfg_path()):
        shutil.copy(os.path.join(SKILL_ROOT, "config.example.json"), cfg_path())
    # 把实际输出根目录写回 config，否则后续子命令会回退到默认路径
    cfg = load_json(cfg_path(), {})
    cfg.setdefault("output", {})["root"] = root
    json.dump(cfg, open(cfg_path(), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    if not os.path.exists(profile_path()):
        shutil.copy(os.path.join(SKILL_ROOT, "resume_profile.example.json"), profile_path())
    for sub in ("jd", "logs", "raw"):
        ensure(os.path.join(root, sub))
    print(json.dumps({"root": root, "config": cfg_path(), "profile": profile_path()},
                     ensure_ascii=False, indent=1))
    print("\n目录已建好。下一步：填 config.json 和 resume_profile.json，然后跑 doctor。")


def cmd_doctor(a):
    rep = {"ok": True, "items": []}

    def add(name, ok, detail, fix=""):
        # ok=None 表示「脚本无法自检，需 agent 确认」，不算失败
        rep["items"].append({"name": name, "ok": ok, "detail": detail, "fix": fix})
        if ok is False:
            rep["ok"] = False

    bsk = shutil.which("bsk")
    add("bsk CLI（备用驱动）", bool(bsk), bsk or "不在 PATH",
        "备用驱动。若要用：把 bsk.exe 放进 PATH，或在连接器里启用 browser-skill")
    add("chrome-devtools MCP（主驱动）", None,
        "脚本无法自检——请 agent 调 list_pages 确认",
        "在连接器面板启用 chrome-devtools；或改用 bsk")
    cfg = os.path.exists(cfg_path())
    add("config.json", cfg, cfg_path() if cfg else "缺失", "跑 workflow.py init 生成后填写")
    prof = os.path.exists(profile_path())
    add("resume_profile.json", prof, profile_path() if prof else "缺失",
        "跑 workflow.py init 生成后填写（不填就没有防误投能力）")
    root = root_of(load_json(cfg_path(), {}))
    add("输出目录", os.path.isdir(root), root, "跑 workflow.py init 重建")
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    if not rep["ok"]:
        print("\n有缺失项，按上面 fix 处理后再跑。", file=sys.stderr)


def cmd_ingest(a):
    rows = json.load(open(a.raw, encoding="utf-8")) if a.raw else json.load(sys.stdin)
    for r in rows:
        r.setdefault("platform", a.platform)
    uniq = dedup(rows)
    cfg = load_json(cfg_path(), {})
    p = paths(root_of(cfg), a.date, a.platform)
    json.dump(uniq, open(p["raw_file"], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"in": len(rows), "uniq": len(uniq), "saved": p["raw_file"]},
                     ensure_ascii=False))


def cmd_screen(a):
    prof = load_json(profile_path(), {})
    cfg = load_json(cfg_path(), {})
    if a.job:
        job, jd = json.load(open(a.job, encoding="utf-8")), (a.jd or "")
    else:
        blob = json.load(sys.stdin)
        job, jd = blob.get("job", {}), blob.get("jd", "")
    r = screen(job, jd, prof, cfg)
    # 保存 JD
    pk = job.get("pk") or str(int(time.time()))
    p = paths(root_of(cfg), a.date, job.get("platform") or a.platform)
    d = os.path.join(p["jd_platform"], re.sub(r"[^\w\-]", "_", pk) + ".json")
    json.dump({**job, "jd": jd, "screen": r, "ts": time.strftime("%Y-%m-%d %H:%M:%S")},
              open(d, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    md = os.path.join(p["jd_platform"], re.sub(r"[^\w\-]", "_", pk) + ".md")
    open(md, "w", encoding="utf-8").write(
        "# %s | %s\n\n- 城市：%s\n- 薪资：%s\n- 筛选：%s（%d 分）\n- 建议简历：%s\n\n## JD\n\n%s\n"
        % (job.get("name", ""), job.get("company", ""), job.get("city", ""),
           job.get("salary", ""), "放行" if r["pass"] else "跳过", r["score"],
           r["resume"], (jd or "")[:6000]))
    r["saved"] = {"json": d, "md": md}
    print(json.dumps(r, ensure_ascii=False, indent=1))


def cmd_log(a):
    cfg = load_json(cfg_path(), {})
    p = paths(root_of(cfg), a.date, a.platform)
    rec = json.load(open(a.record, encoding="utf-8")) if a.record else json.load(sys.stdin)
    rec.setdefault("ts", time.strftime("%Y-%m-%d %H:%M:%S"))
    rec.setdefault("platform", a.platform)
    with open(p["log_file"], "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps({"appended": p["log_file"], "result": rec.get("result")}, ensure_ascii=False))


def cmd_report(a):
    cfg = load_json(cfg_path(), {})
    date = a.date or time.strftime("%Y-%m-%d")
    p = paths(root_of(cfg), date, a.platform)
    records = []
    if os.path.exists(p["log_file"]):
        for line in open(p["log_file"], encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    records = dedup_success_first(records)
    if not records:
        print("没有日志记录，跳过")
        return
    fn = os.path.join(p["log"], "投递汇总-%s-%s.md" % (date, a.platform))
    open(fn, "w", encoding="utf-8").write(round_report(records, date, a.platform))
    total = os.path.join(root_of(cfg), "投递汇总报告.md")
    tot_n, tot_ok = update_total(date, a.platform, records, total)
    n = keyword_summary(os.path.join(root_of(cfg), "jd"),
                        os.path.join(root_of(cfg), "已查看岗位JD关键词总结.md"))
    print(json.dumps({"round": fn, "total": total, "cum": [tot_n, tot_ok], "jd_sample": n},
                     ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="job-auto-apply 工作流")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ini = sub.add_parser("init")
    ini.add_argument("--root", default=None)

    sub.add_parser("doctor")

    ing = sub.add_parser("ingest")
    ing.add_argument("--raw", default=None, help="agent 抓到的卡片 json（不给则从 stdin 读）")
    ing.add_argument("--platform", required=True)
    ing.add_argument("--date", default=None)

    sc = sub.add_parser("screen")
    sc.add_argument("--job", default=None, help="岗位 json（不给则从 stdin 读 {\"job\":{},\"jd\":\"\"}）")
    sc.add_argument("--jd", default=None)
    sc.add_argument("--platform", default="iguopin")
    sc.add_argument("--date", default=None)

    lg = sub.add_parser("log")
    lg.add_argument("--record", default=None)
    lg.add_argument("--platform", required=True)
    lg.add_argument("--date", default=None)

    rp = sub.add_parser("report")
    rp.add_argument("--platform", required=True)
    rp.add_argument("--date", default=None)

    a = ap.parse_args()
    {"init": cmd_init, "doctor": cmd_doctor, "ingest": cmd_ingest,
     "screen": cmd_screen, "log": cmd_log, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
