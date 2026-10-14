# -*- coding: utf-8 -*-
"""bsk 薄封装：所有平台脚本共用。

依赖：bsk CLI 在 PATH；daemon 已在受管后台任务里启动。
用法：from bskw import Bsk; b = Bsk(session)
"""
import json
import os
import re
import subprocess
import time


class Bsk(object):
    def __init__(self, session, env_override=None):
        self.session = session
        self.env = dict(os.environ)
        self.env["BSK_AUTO_START"] = "0"
        if env_override:
            self.env.update(env_override)

    # ---------- 基础 ----------
    def run(self, args, timeout=60):
        """执行 bsk 子命令，返回 stdout；超时返回空串（绝不抛异常）。"""
        try:
            r = subprocess.run(["bsk"] + args, env=self.env, capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=timeout)
            return r.stdout or ""
        except subprocess.TimeoutExpired:
            return ""
        except Exception:
            return ""

    def ev(self, expr, timeout=60, tab=None):
        """执行 JS 并返回 value。失败返回 None。"""
        a = ["evaluate", expr, "--session", self.session]
        if tab:
            a += ["--tab-id", str(tab)]
        a += ["--json"]
        out = self.run(a, timeout)
        try:
            return json.loads(out).get("value")
        except Exception:
            return None

    def evobj(self, expr, timeout=60, tab=None):
        """执行 JS，返回值是 JSON 字符串时自动解析成 dict。"""
        v = self.ev(expr, timeout, tab)
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {"raw": v}
        return v or {}

    def snap(self, tab=None):
        """取无障碍快照文本（含 @eN ref）。"""
        a = ["snapshot", "--session", self.session]
        if tab:
            a += ["--tab-id", str(tab)]
        a += ["--json"]
        try:
            return json.loads(self.run(a)).get("text", "") or ""
        except Exception:
            return ""

    def navigate(self, url, tab=None, wait=0.0):
        a = ["navigate", url, "--session", self.session]
        if tab:
            a += ["--tab-id", str(tab)]
        a += ["--json"]
        out = self.run(a)
        if wait:
            time.sleep(wait)
        return out

    def click(self, target, tab=None):
        """target 可以是 CSS 选择器或 @eN ref。返回是否命中。"""
        a = ["click", target, "--session", self.session]
        if tab:
            a += ["--tab-id", str(tab)]
        a += ["--json"]
        out = self.run(a)
        return ("used_selector" in out) or ("used_ref" in out)

    def click_js(self, mark_js, selector, tab=None):
        """bsk click 对无可见尺寸的元素会报 not visible。
        解法：先用 JS 给目标打标记属性，再用 CSS 选择器点。"""
        self.ev(mark_js, tab=tab)
        time.sleep(0.4)
        return self.click(selector, tab=tab)

    def tabs(self):
        try:
            return json.loads(self.run(["tab", "list", "--session", self.session,
                                        "--json"])).get("tabs", [])
        except Exception:
            return []

    def work_tab(self):
        """取一个工作标签页；没有就新建。
        注意：详情页可能被开成新 tab，处理完立刻关，避免标签累积读错页。"""
        for t in self.tabs():
            return t["tab_id"]
        out = self.run(["tab", "create", "--session", self.session, "--json"])
        m = re.search(r"tab_id=(\d+)", out or "")
        return m.group(1) if m else None

    # ---------- 快照解析 ----------
    @staticmethod
    def refs_by_name(snap_text, kind="button", name=None):
        """从快照里取 ref 列表：[('12','申请职位'), ...]"""
        out = []
        for r, n in re.findall(r"@e(\d+) %s \"([^\"]*)\"" % kind, snap_text):
            if name is None or n == name:
                out.append((r, n))
        return out

    def click_named(self, snap_text, names, tab=None, kind="button"):
        """按按钮文案点击（去空格后精确匹配）。返回是否点到。"""
        want = {x.replace(" ", "") for x in names}
        for r, n in self.refs_by_name(snap_text, kind):
            if n.replace(" ", "") in want:
                return self.click("@e" + r, tab=tab)
        return False

    # ---------- 通用兜底 ----------
    def poll_js(self, js, expect, max_wait=9.0, interval=0.7, tab=None):
        """轮询执行 JS 直到返回值 != expect。返回最后的状态值。"""
        waited = 0.0
        state = expect
        while waited < max_wait:
            state = self.ev(js, tab=tab) or expect
            if state != expect:
                break
            time.sleep(interval)
            waited += interval
        return state

    def wait_button(self, text, max_wait=9.0, tab=None, retries=6):
        """等按钮出现并拿到 ref。三层：JS 轮询 -> 快照重复取 -> 返回 ('Y'/'DISABLED'/'N', refs)

        只靠 snapshot ref 会大批误杀（快照树滞后），必须带 JS 兜底。
        """
        js = ('(function(){var bs=Array.from(document.querySelectorAll("button"));'
              'for(var i=0;i<bs.length;i++){if(bs[i].innerText.replace(/\\s/g,"")==="%s")'
              'return bs[i].disabled?"DISABLED":"Y";}return "N";})()' % text)
        state = self.poll_js(js, "N", max_wait, tab=tab)
        if state == "N":
            return "N", []
        for _ in range(retries):
            refs = [r for r, n in self.refs_by_name(self.snap(tab=tab)) if n == text]
            if refs:
                return state, refs
            time.sleep(0.7)
        return state, []

    def js_click_button(self, text, tab=None):
        """拿不到 ref 时的兜底：真实 JS 点击。"""
        js = ('(function(){var bs=Array.from(document.querySelectorAll("button"));'
              'for(var i=0;i<bs.length;i++){if(bs[i].innerText.replace(/\\s/g,"")==="%s")'
              '{if(bs[i].disabled)return "disabled";bs[i].click();return "clicked";}}'
              'return "notfound";})()' % text)
        return self.ev(js, tab=tab)
