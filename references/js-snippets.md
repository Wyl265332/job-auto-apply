# JS 片段库

全部给 `mcp__chrome-devtools__evaluate_script` 的 `function` 参数用。
**注意：function 是 JSON 字符串，正则里的 `\s` 必须写成 `\\s`。**

---

## 环境自检

### 登录态 + 页面概览

```js
() => {
  const t = document.body ? document.body.innerText : '';
  const btns = Array.from(document.querySelectorAll('button'))
    .map(b => ({txt:(b.innerText||'').trim(), disabled:b.disabled}))
    .filter(x => x.txt && x.txt.length < 20);
  return {
    title: document.title, len: t.length,
    btns: btns.slice(0,30), head: t.slice(0,400),
    loginWall: /扫码登录|密码登录|短信验证码|欢迎来到智联招聘|请先登录/.test(t)
  };
}
```

---

## 抓取

### 抓取-国聘卡片（React fiber，列表页免登录可抓）

```js
() => Array.from(document.querySelectorAll('.job-card')).map(function(c){
 var q=function(s){var e=c.querySelector(s);return e?e.textContent.trim():""};
 var fk=Object.keys(c).filter(function(k){return k.indexOf("__reactFiber")===0})[0];
 var j=null;
 if(fk){var n=c[fk]&&c[fk].return; if(n&&n.memoizedProps&&n.memoizedProps.job) j=n.memoizedProps.job;}
 j=j||{};
 return {pk:j.job_id||"", name:j.job_name||q(".job-name"), company:q(".company-name"),
  company_id:j.company_id||"", dist:q(".job-district"), salary:q(".job-salary"),
  dept:q(".department-name"),
  tags:Array.from(c.querySelectorAll(".job-info .tag-item")).map(x=>x.textContent.trim()),
  applied:(typeof j.applied!=="undefined")?j.applied:null,
  edu:j.education_cn||j.education||"", rec:j.recruitment_type_cn||"",
  url:j.job_id?("https://www.iguopin.com/job/detail?id="+j.job_id):""};
})
```

实测 20/20 命中。`applied == 2` 才是未投递。

### 抓取-智联卡片（Vue `$props.job`，含详情直链）

```js
() => Array.from(document.querySelectorAll('div.job-card:not(.job-card--active)')).map(function(c){
 try{
  var j=c.__vue__ && c.__vue__.$props ? c.__vue__.$props.job : null;
  if(!j||!j.jobId) return null;
  return {pk:String(j.jobId), name:j.name, company:j.companyName,
   url:j.positionURL||j.positionUrl||"", edu:j.education||"", exp:j.workingExp||"",
   workType:j.workType||"", salary:j.salary60||j.salaryReal||"", city:j.workCity||"",
   dist:j.cityDistrict||"", industry:j.industryName||"", scale:j.companySize||"",
   jd:(j.jobDescription||"").slice(0,3000)};
 }catch(e){return null}
}).filter(x=>x)
```

实测 19/19 命中，免登录。

### 抓取-实习僧卡片（DOM 解析即可，主键是 URL 里的 inn_xxx）

```js
() => Array.from(document.querySelectorAll('.intern-item')).map(function(it){
 var a=it.querySelector('a[href]');
 var href=a?a.getAttribute('href'):'';
 var m=href.match(/inn_[a-z0-9]+/);
 var txt=(it.innerText||'').split('\n').map(s=>s.trim()).filter(Boolean);
 return {pk:m?m[0]:'', url:href.indexOf('http')===0?href:('https://www.shixiseng.com'+href),
  name:txt[0]||'', salary:txt[1]||'', city:(txt[2]||'').split('|')[0].trim(),
  edu:/本科|硕士|大专/.test(txt[2]||'')?(txt[2].match(/本科|硕士|大专/)||[''])[0]:'',
  company:txt[3]||'', tags:txt.slice(3,9)};
})
```

实测 20/20 命中。卡片自带「应届生 / 本科」，校招场景很好用。

### 抓取-51job 卡片（仅列表，详情会撞滑块）

```js
() => Array.from(document.querySelectorAll('.joblist-item')).map(function(it){
 var a=it.querySelector('a[href]');
 var href=a?a.getAttribute('href'):'';
 var m=href.match(/co[A-Za-z0-9]+\.html/);
 var txt=(it.innerText||'').split('\n').map(s=>s.trim()).filter(Boolean);
 return {pk:m?m[0].replace('.html',''):'', url:href,
  name:txt[0]||'', salary:txt[1]||'', city:txt[2]||'',
  company:txt[txt.length-3]||'', tags:txt.slice(3,9)};
})
```

### 实习僧投递按钮（注意是 div 不是 button）

```js
() => {
  const e = document.querySelector('.resume_apply');
  if (!e) return {found:false};
  const r = e.getBoundingClientRect();
  return {found:true, cls:String(e.className), txt:(e.innerText||'').trim(),
          w:Math.round(r.width), h:Math.round(r.height), visible:r.width>0&&r.height>0};
}
```

实测：`.btn-box.resume_apply.com_res`，文案「投个简历」，131×61 可见。

### 找投递按钮的通用兜底（按钮不是 button 时用它）

```js
() => {
  const kw = ['投递','申请','投简历','投个简历','立即沟通','应聘'];
  const out = [];
  document.querySelectorAll('*').forEach(e => {
    if (e.children.length !== 0) return;
    const x = (e.innerText || e.textContent || '').trim();
    if (x && x.length < 12 && kw.some(k => x.includes(k))) {
      const r = e.getBoundingClientRect();
      out.push({tag:e.tagName, cls:String(e.className).slice(0,50), txt:x,
                w:Math.round(r.width), h:Math.round(r.height)});
    }
  });
  return out.slice(0,20);
}
```

**注意：未登录时按钮可能是 0 尺寸**（隐藏）。0 尺寸不代表没有，登录后才会显示。

### 国聘列表页切「校招」

即使有遮罩，JS click 依然有效：

```js
() => {
  var t=Array.from(document.querySelectorAll("*")).filter(
    n => n.childElementCount===0 && n.textContent.trim()==="校招");
  if(t.length) t[0].click();
  return "ok";
}
```

---

## JD 门禁

### JD门禁（切正文 + 判定，一次性返回）

```js
() => {
  const t = document.body ? document.body.innerText : '';
  const S = ['职位描述','岗位职责','职位职责','任职要求'];
  const E = ['工作地点','公司信息','工商信息','相似职位','以担保或任何理由','举报'];
  let i=-1, j=-1;
  S.forEach(s => {const p=t.indexOf(s); if(p>=0&&(i<0||p<i)) i=p;});
  E.forEach(e => {const p=t.indexOf(e, i>=0?i:0); if(p>=0&&(j<0||p<j)) j=p;});
  const jd = i>=0 ? t.slice(i, (j>i? j : i+3000)) : t.slice(0,1200);
  const NEG = [/[1-9]\s*年以上[\s\S]{0,8}经验/,
                /要求[\s\S]{0,4}[1-9]\s*年[\s\S]{0,4}经验/,
                /[1-9]-[1-9]年经验/];
  let neg=null;
  for (const p of NEG) { const m = jd.match(p); if (m) { neg = m[0]; break; } }
  const MUST = ['校招','校园招聘','应届','应届生','在校生'];  // 加自己的届别，如 '2027届'
  const hits = MUST.filter(k => jd.includes(k));
  return {title:document.title, jdStart:i, jdEnd:j, jdLen:jd.length,
          jd:jd.slice(0,3000), negExp:neg, mustHits:hits,
          gate: hits.length>0 && !neg,
          truncated: /登录查看完整内容|登录后查看/.test(jd)};
}
```

三个要点：

1. **判定文本只取 JD 正文**。智联导航栏自带「校招」入口，用页面头部会 100% 误命中。
2. **届别词常只出现在岗位标题里**，JD 正文没有 → 门禁会判 false。
   正式判定要把 `name + jd` 合并（见 `pipeline.py` 的 `jd_gate`）。
3. **未登录时智联 JD 被截断**（末尾「登录查看完整内容」），`truncated` 会标 true，
   此时门禁结果不可信，必须先登录。

---

## 按钮与弹窗

### 找按钮（返回文案 + disabled，用来判断点之前的状态）

```js
() => {
  const btns = Array.from(document.querySelectorAll('button'))
    .map(b => ({txt:(b.innerText||'').trim().replace(/\s/g,''), disabled:b.disabled}))
    .filter(x => x.txt && x.txt.length < 20);
  const target = ['申请职位','立即投递'];
  return {btns: btns.slice(0,30),
          hasTarget: btns.filter(b => target.includes(b.txt)),
          delivered: /已申请|已投递|继续沟通|投递成功/.test(document.body.innerText)};
}
```

用 chrome-devtools 时，**优先 `take_snapshot` 拿 uid 再 `click`**，比 JS 点击稳，
也不用处理"元素不可见"。这段 JS 只用来在读阶段判断状态。

### 读弹窗（取最后一个可见 modal）

```js
() => {
  const sels = ['.ant-modal-wrap .ant-modal', '.a-modal', '[class*=modal]', '[class*=dialog]'];
  const found = {};
  for (const s of sels) {
    const els = Array.from(document.querySelectorAll(s))
      .filter(e => {const r=e.getBoundingClientRect(); return r.width>50 && r.height>50;});
    if (els.length) found[s] = els.map(e => ({
      cls: String(e.className).slice(0,80),
      txt: (e.innerText||'').slice(0,300),
      btns: Array.from(e.querySelectorAll('button,a'))
        .map(b=>(b.innerText||'').trim()).filter(t=>t&&t.length<20).slice(0,15)
    })).slice(0,2);
  }
  return {found, url: location.href};
}
```

弹窗分类（按顺序判定，先排除登录框）：

| 弹窗内容 | 动作 |
|---|---|
| 欢迎来到智联招聘 / 验证码登录 / 请先登录 | **登录墙 → 停止并让用户登录** |
| 专属简历模板 / 需先完善信息 / 完善简历 / 创建简历 / 必填 | 取消 → skip |
| 验证码 | 取消 → **停止整个任务** |
| 请选择要投递的简历 / 在线简历 | 选简历 → 点确认 |
| 最多可投递 / 已达上限 / 只能投递 | 取消 → skip，集团加黑名单 |
| 成功 / 已投递 | 记 ok |

### 结果判定（确认之后）

```js
() => {
  const body = (document.body.innerText||'').slice(0,1500);
  const btns = Array.from(document.querySelectorAll('button'))
    .map(b=>(b.innerText||'').trim()).filter(t=>t&&t.length<15);
  return {ok: /投递成功|已申请|已投递|继续沟通/.test(body),
          btnHas: btns.filter(t=>/继续沟通|已投递/.test(t)),
          btns: btns.slice(0,15), url: location.href};
}
```

---

## 收尾

### 收藏当前职位（已收藏则跳过）

```js
() => {
  var b=Array.from(document.querySelectorAll('button'))
    .filter(x => /收.{0,2}藏/.test(x.textContent));
  if(!b.length) return 'nofav';
  if(/已收藏/.test(b[0].textContent)) return 'already';
  b[0].click(); return 'fav';
}
```

### 智联后台已投记录（page 参数无效，要点翻页）

```
https://i.zhaopin.com/schedule?status=delivered
```

翻页点 `.ivu-page-next`。**不要用 URL 的 page 参数**，会重复计数。
