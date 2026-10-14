# -*- coding: utf-8 -*-
"""一键安装 / 环境准备

用法：
    python setup.py --driver chrome-devtools      # 主驱动
    python setup.py --driver bsk                  # 备用驱动
    python setup.py --driver both
    python setup.py --check                       # 只体检，不装

能自动做的自动做（建目录、生成配置、把 bsk 加进 PATH 检测）；
做不到自动的（MCP 启用、浏览器扩展安装）打印明确的人工步骤，不假装装好了。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
DEFAULT_ROOT = os.path.join(os.path.expanduser("~"), "Documents", "投递记录")

MANUAL = {
    "chrome-devtools": [
        "在主界面左下角「+」→ 连接器管理里找到 chrome-devtools，点启用",
        "（若列表里没有）到连接器市场搜索 chrome-devtools 并安装",
        "启用后回来让我调一次 list_pages，能返回页面列表就算通",
    ],
    "bsk": [
        "bsk CLI 未安装时，两条路任选：",
        "  1) 把已有的 bsk.exe 放到 PATH 里的目录（本机示例 C:\\Users\\<你>\\.local\\bin\\）",
        "  2) 在连接器里启用 browser-skill，按它的说明装 CLI 与浏览器扩展",
        "浏览器扩展需在 Chrome/Edge 里手动安装并开启连接",
    ],
}


def sh(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return -1, str(e)


def check_bsk():
    return shutil.which("bsk")


def try_install_bsk():
    """尽力而为：试几种常见安装方式，都不行就返回人工步骤。"""
    for cmd in ["winget install bsk", "npm i -g browser-skill",
                "pip install browser-skill"]:
        rc, out = sh(cmd)
        if rc == 0:
            return True, "已通过 `%s` 安装" % cmd
    return False, "自动安装未成功（本机没有可用的包管理器或包不存在）"


def ensure_dirs(root, driver):
    for sub in ("jd", "logs", "raw"):
        p = os.path.join(root, sub)
        if not os.path.exists(p):
            os.makedirs(p)
    cfgp = os.path.join(os.getcwd(), "config.json")
    if not os.path.exists(cfgp):
        shutil.copy(os.path.join(SKILL_ROOT, "config.example.json"), cfgp)
        cfg = json.load(open(cfgp, encoding="utf-8"))
        cfg.setdefault("output", {})["root"] = root
        cfg["driver"] = driver
        json.dump(cfg, open(cfgp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    profp = os.path.join(os.getcwd(), "resume_profile.json")
    if not os.path.exists(profp):
        shutil.copy(os.path.join(SKILL_ROOT, "resume_profile.example.json"), profp)
    return cfgp, profp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--driver", choices=["chrome-devtools", "bsk", "both"], default=None)
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    report = {"bsk": check_bsk(), "auto": [], "manual": []}

    if a.check:
        print(json.dumps({"bsk": report["bsk"] or "未安装"}, ensure_ascii=False, indent=1))
        return

    driver = a.driver or "chrome-devtools"

    if driver in ("bsk", "both"):
        if not check_bsk():
            ok, msg = try_install_bsk()
            report["auto"].append("bsk: " + msg)
            if not ok:
                report["manual"] += MANUAL["bsk"]
        else:
            report["auto"].append("bsk: 已就绪 -> %s" % check_bsk())

    if driver in ("chrome-devtools", "both"):
        # MCP 由宿主管理，脚本装不了，只能给人工步骤
        report["manual"] += MANUAL["chrome-devtools"]

    cfgp, profp = ensure_dirs(a.root, driver)
    report["auto"].append("目录与配置已就绪 -> %s" % a.root)
    report["config"] = cfgp
    report["profile"] = profp

    print(json.dumps(report, ensure_ascii=False, indent=1))
    if report["manual"]:
        print("\n需要你手动完成：", file=sys.stderr)
        for i, s in enumerate(report["manual"], 1):
            print("  %d. %s" % (i, s), file=sys.stderr)
    print("\n下一步：填 %s 和 %s，然后跑 workflow.py doctor" % (cfgp, profp))


if __name__ == "__main__":
    main()
