// 声眼舆情监测 V1 前端（工作台版），直接调用 /api/v1
(() => {
  const API = '/api/v1';
  const SENT = { neg: '负面', neu: '中性', pos: '正面' };
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmtNum = n => n >= 10000 ? (n / 10000).toFixed(1) + '万' : String(n ?? 0);

  const state = {
    user: null, page: 'feed',
    summary: null, groups: [], limits: { max_groups: 3, max_words: 20 },
    hits: [], cursor: null, loading: false, newCount: 0,
    f: { group: '', sentiment: '', status: 'open', q: '' },
    notify: null, users: [], editing: null, flashId: null,
  };
  try { const p = localStorage.getItem('sy.page'); if (p) state.page = p; } catch (e) {}

  // ---------- 工具 ----------
  async function api(path, opts = {}) {
    const res = await fetch(API + path, {
      method: opts.method || 'GET', credentials: 'same-origin',
      headers: opts.body ? { 'Content-Type': 'application/json' } : {},
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch (e) {}
    if (res.status === 401 && !opts.allow401) { state.user = null; render(); throw new Error(data?.message || '请先登录'); }
    if (!res.ok) throw new Error(data?.message || `请求失败（${res.status}）`);
    return data;
  }

  function toast(msg) {
    document.querySelectorAll('.toast').forEach(t => t.remove());
    const t = document.createElement('div');
    t.className = 'toast'; t.setAttribute('role', 'status'); t.textContent = msg;
    document.body.appendChild(t); setTimeout(() => t.remove(), 2600);
  }
  const fail = e => toast(e.message || String(e));

  function fmtTime(iso) {
    if (!iso) return '';
    const d = new Date(iso), now = new Date();
    const hm = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
    const day = x => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const diff = (day(now) - day(d)) / 86400000;
    if (diff === 0) return hm;
    if (diff === 1) return '昨天 ' + hm;
    return `${d.getMonth() + 1}月${d.getDate()}日 ${hm}`;
  }

  function hl(text, word) {
    let out = esc(text);
    (word || '').split(/\s+/).filter(Boolean).forEach(k => {
      const e = esc(k);
      out = out.split(e).join('<mark>' + e + '</mark>');
    });
    return out;
  }

  function hitsQuery(extra = {}) {
    const p = new URLSearchParams();
    if (state.f.group) p.set('group_id', state.f.group);
    if (state.f.sentiment) p.set('sentiment', state.f.sentiment);
    p.set('status', state.f.status);
    if (state.f.q) p.set('q', state.f.q);
    Object.entries(extra).forEach(([k, v]) => v != null && p.set(k, v));
    return p.toString();
  }

  // ---------- 数据加载 ----------
  async function loadSummary() { state.summary = await api('/summary'); }
  async function loadGroups() { const d = await api('/keyword-groups'); state.groups = d.items; state.limits = d.limits; }
  async function loadHits(reset = true) {
    state.loading = true;
    try {
      const d = await api('/hits?' + hitsQuery({ limit: 20, cursor: reset ? null : state.cursor }));
      state.hits = reset ? d.items : state.hits.concat(d.items);
      state.cursor = d.next_cursor;
      if (reset) state.newCount = 0;
    } finally { state.loading = false; }
  }
  async function loadSettings() {
    const [n, u] = await Promise.all([api('/settings/notify'), api('/users')]);
    state.notify = n; state.users = u.items;
  }

  async function go(page) {
    state.page = page;
    try { localStorage.setItem('sy.page', page); } catch (e) {}
    render();
    try {
      if (page === 'feed') await Promise.all([loadSummary(), loadGroups(), loadHits()]);
      if (page === 'keywords') await Promise.all([loadGroups(), loadSummary()]);
      if (page === 'settings') await Promise.all([loadSettings(), loadSummary()]);
    } catch (e) { fail(e); }
    render();
    if (state.flashId) {
      const el = document.getElementById('hit-' + state.flashId);
      if (el) { el.classList.add('flash'); el.scrollIntoView({ block: 'center' }); }
      state.flashId = null;
    }
  }

  // ---------- 登录 ----------
  function renderLogin() {
    return `<div class="login"><form class="login-card" id="loginForm">
      <h1><span class="logo-mark" aria-hidden="true"></span>声眼舆情监测</h1>
      <p>用管理员邀请的手机号登录。</p>
      <label>手机号<input class="input" id="lgPhone" inputmode="tel" autocomplete="tel" maxlength="11" placeholder="11 位手机号"></label>
      <label>验证码<div class="code-row"><input class="input" id="lgCode" inputmode="numeric" maxlength="6" placeholder="6 位验证码" autocomplete="one-time-code">
        <button type="button" class="btn" id="sendCode">获取验证码</button></div></label>
      <div class="err" id="lgErr"></div>
      <button class="btn primary">登录</button>
    </form></div>`;
  }

  // ---------- 布局 ----------
  function shell(inner) {
    const negOpen = state.summary?.neg_open_total ?? 0;
    const nav = (p, label) => `<button data-page="${p}" aria-current="${state.page === p ? 'page' : 'false'}">${label}${p === 'feed' && negOpen ? ` <span class="count">${negOpen}</span>` : ''}</button>`;
    return `<div class="app">
      <aside class="side">
        <div class="logo"><span class="logo-mark" aria-hidden="true"></span>声眼</div>
        <nav class="nav" aria-label="主导航">${nav('feed', '信息流')}${nav('keywords', '关键词管理')}${nav('settings', '设置')}</nav>
        <div class="side-foot"><div class="side-user"><span>${esc(state.user.name)} · ${state.user.role === 'admin' ? '管理员' : '成员'}</span>
          <button class="link" data-act="logout">退出</button></div>小红书 · 单租户 V1</div>
      </aside>
      <main id="main">${inner}</main></div>`;
  }

  function systemBanner() {
    const s = state.summary?.system;
    if (!s) return '';
    const isAdmin = state.user.role === 'admin';
    if (s.state === 'auth_failed') return `<div class="banner warn">${esc(s.message)}${isAdmin ? '<button class="btn" data-act="resume">已更换 Token，恢复采集</button>' : ''}</div>`;
    if (['paused', 'delayed'].includes(s.state)) return `<div class="banner warn">${esc(s.message)}</div>`;
    if (s.state === 'idle') return `<div class="banner">还没有启用的关键词组。<button class="btn" data-page="keywords">去添加关键词</button></div>`;
    if (s.state === 'starting') return `<div class="banner">正在进行首次采集，稍后刷新即可看到内容。</div>`;
    return '';
  }

  function modeTags() {
    const s = state.summary?.system;
    if (!s) return '';
    const tags = [];
    if (s.crawler_mode === 'mock') tags.push('<span class="pill">演示数据源（未配置 TikHub Token）</span>');
    if (s.sentiment_mode === 'rule') tags.push('<span class="pill">规则情感（未配置 DeepSeek Key）</span>');
    return tags.length ? `<div class="mode">${tags.join('')}</div>` : '';
  }

  // ---------- 信息流 ----------
  function seg(name, opts) {
    return '<div class="seg" role="group">' + opts.map(([v, l]) =>
      `<button data-seg="${name}" data-v="${v}" aria-pressed="${state.f[name] === v}">${l}</button>`).join('') + '</div>';
  }

  function renderFeed() {
    const s = state.summary || {};
    const sys = s.system || {};
    const negRate = s.today_hits ? Math.round(s.today_neg / s.today_hits * 100) : 0;
    return `
    <div class="head"><div><h1>信息流</h1><p>小红书 · 每 ${sys.interval_min || 10} 分钟更新 · 最近一次成功采集 ${sys.last_success_at ? fmtTime(sys.last_success_at) : '—'}</p></div>${modeTags()}</div>
    ${systemBanner()}
    <section class="kpis" aria-label="今日概况">
      <div class="kpi"><div class="label">今日命中</div><div class="num">${s.today_hits ?? '—'}</div><div class="sub">${s.enabled_groups ?? 0} 个关键词组</div></div>
      <div class="kpi neg"><div class="label">今日负面</div><div class="num">${s.today_neg ?? '—'}</div><div class="sub">占比 ${negRate}%</div></div>
      <div class="kpi"><div class="label">今日预警</div><div class="num">${s.today_alerts ?? '—'}</div><div class="sub">已推送或排队中</div></div>
      <div class="kpi"><div class="label">负面待处理</div><div class="num">${s.neg_open_total ?? '—'}</div><div class="sub">标记已处理后移出</div></div>
    </section>
    <div class="filters">
      <select id="fGroup" aria-label="关键词组"><option value="">全部关键词组</option>${state.groups.map(g => `<option value="${g.id}" ${String(state.f.group) === String(g.id) ? 'selected' : ''}>${esc(g.name)}</option>`).join('')}</select>
      ${seg('sentiment', [['', '全部'], ['neg', '负面'], ['neu', '中性'], ['pos', '正面'], ['pending', '待判断']])}
      ${seg('status', [['open', '待处理'], ['done', '已处理'], ['all', '全部']])}
      <input class="input grow" id="fQ" type="search" placeholder="搜索标题、正文、作者" value="${esc(state.f.q)}" style="min-width:140px">
      <a class="btn" id="export" href="${API}/hits/export?${hitsQuery()}">导出 Excel</a>
    </div>
    ${state.newCount ? `<div class="newbar"><button data-act="refresh">有新内容，点击刷新</button></div>` : ''}
    <div class="feed">${state.hits.length ? state.hits.map(postHTML).join('') : `<div class="empty">${state.loading ? '加载中…' : '没有符合条件的内容。'}</div>`}</div>
    ${state.cursor ? `<div class="more"><button class="btn" data-act="more" ${state.loading ? 'disabled' : ''}>加载更多</button></div>` : ''}`;
  }

  function postHTML(h) {
    const p = h.post;
    const sent = h.sentiment;
    return `<article class="post s-${sent || 'none'} ${h.status === 'done' ? 'done' : ''}" id="hit-${h.id}">
      <div class="stripe" aria-hidden="true"></div>
      <div style="min-width:0">
        <div class="meta">
          <span class="plat p-xhs"><i></i>小红书</span>
          <span>${esc(p.author_name || '未知作者')}</span><span title="${esc(p.published_at)}">${fmtTime(p.published_at)}${p.published_at_estimated ? '（采集时间）' : ''}</span>
          ${sent ? `<span class="pill ${sent}" title="${esc(h.reason)}">${SENT[sent]}${h.manual ? ' · 人工' : ` ${Math.round(h.confidence * 100)}%`}</span>` : '<span class="pill pending">待判断</span>'}
          <span class="pill kw">${esc(h.group.name)} · ${esc(h.matched_word)}</span>
          ${h.alert_id ? '<span class="pill alerted">已预警</span>' : ''}
          ${h.is_backfill ? '<span class="pill backfill">回溯</span>' : ''}
          ${h.similar_count ? `<span>相似 ${h.similar_count} 篇</span>` : ''}
        </div>
        ${p.title ? `<h3>${hl(p.title, h.matched_word)}</h3>` : ''}
        <p>${hl(p.content, h.matched_word)}</p>
        <div class="row-foot">
          <span>赞 ${fmtNum(p.like)}</span><span>评 ${fmtNum(p.comment)}</span><span>藏 ${fmtNum(p.collect)}</span><span>转 ${fmtNum(p.share)}</span>
          <div class="acts">
            <label style="display:inline-flex;align-items:center;gap:4px">改情感
              <select data-act="sent" data-id="${h.id}" id="sent-${h.id}"><option value="" ${!sent ? 'selected' : ''} disabled>待判断</option>${Object.entries(SENT).map(([k, v]) => `<option value="${k}" ${sent === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
            ${h.alert_id ? `<button class="link" data-act="alert" data-id="${h.alert_id}">预警详情</button>` : ''}
            <button class="link" data-act="irrelevant" data-id="${h.id}">不相关</button>
            <button class="link" data-act="done" data-id="${h.id}" data-status="${h.status}">${h.status === 'done' ? '恢复待处理' : '标记已处理'}</button>
            <a class="link" href="${esc(p.url)}" target="_blank" rel="noopener">原文</a>
          </div>
        </div>
      </div>
    </article>`;
  }

  // ---------- 关键词 ----------
  function renderKeywords() {
    const isAdmin = state.user.role === 'admin';
    const full = state.groups.length >= state.limits.max_groups;
    const ed = state.editing ? state.groups.find(g => g.id === state.editing) : null;
    const formDisabled = !isAdmin || (full && !ed);
    return `
    <div class="head"><div><h1>关键词管理</h1><p>监测词之间为“或”，含空格的词要求每一段都出现；命中排除词的内容直接丢弃。新建后自动回溯近 3 天。</p></div>
      <span class="quota">已用 ${state.groups.length} / ${state.limits.max_groups} 组 · 每组最多 ${state.limits.max_words} 个词</span></div>
    ${systemBanner()}
    <div class="groups">
      ${state.groups.map(g => `<div class="card">
        <h3>${esc(g.name)}<button class="switch" role="switch" aria-checked="${g.enabled}" aria-label="启用 ${esc(g.name)}" data-act="toggleGroup" data-id="${g.id}" ${isAdmin ? '' : 'disabled'}></button></h3>
        <div class="lbl">监测词 · ${g.words.length}/${state.limits.max_words}</div>
        <div class="chips">${g.words.map(w => `<span class="chip">${esc(w)}</span>`).join('')}</div>
        <div class="lbl">排除词</div>
        <div class="chips">${g.exclude_words.length ? g.exclude_words.map(w => `<span class="chip ex">${esc(w)}</span>`).join('') : '<span class="quota">无</span>'}</div>
        <div class="lbl">平台</div>
        <div class="chips"><span class="plat p-xhs" style="font-size:12px"><i></i>小红书</span></div>
        <div class="row-foot" style="margin-top:14px"><span>今日命中 ${g.today_hits} 条</span>
          ${isAdmin ? `<div class="acts"><button class="link" data-act="editGroup" data-id="${g.id}">编辑</button>
          <button class="link danger" data-act="delGroup" data-id="${g.id}">${state.confirmDel === g.id ? '确认删除？' : '删除'}</button></div>` : ''}</div>
      </div>`).join('')}
      <form class="card" id="groupForm">
        <h3>${ed ? `编辑「${esc(ed.name)}」` : '新建关键词组'}</h3>
        ${!isAdmin ? '<div class="readonly-note">只有管理员可以新建或修改关键词组。</div>' : ''}
        <label>名称<input class="input" id="ngName" maxlength="20" placeholder="例如：品牌词" value="${esc(ed?.name || '')}" ${formDisabled ? 'disabled' : ''}></label>
        <label>监测词（逗号或换行分隔）<textarea class="input" id="ngWords" placeholder="山岚咖啡, 山岚 门店" ${formDisabled ? 'disabled' : ''}>${esc((ed?.words || []).join(', '))}</textarea></label>
        <label>排除词（选填）<input class="input" id="ngEx" placeholder="招聘, 转让" value="${esc((ed?.exclude_words || []).join(', '))}" ${formDisabled ? 'disabled' : ''}></label>
        <div class="checks"><label><input type="checkbox" checked disabled>小红书</label><span class="quota">V1 仅支持小红书</span></div>
        <div class="err" id="ngErr">${full && !ed && isAdmin ? `最多 ${state.limits.max_groups} 组，删除一组后可新建。` : ''}</div>
        <div class="inline-actions"><button class="btn primary" ${formDisabled ? 'disabled' : ''}>${ed ? '保存修改' : '保存并开始监测'}</button>
          ${ed ? '<button type="button" class="btn" data-act="cancelEdit">取消</button>' : ''}</div>
      </form>
    </div>`;
  }

  // ---------- 设置 ----------
  function renderSettings() {
    const n = state.notify;
    const isAdmin = state.user.role === 'admin';
    const sys = state.summary?.system || {};
    if (!n) return `<div class="head"><div><h1>设置</h1></div></div><div class="empty">加载中…</div>`;
    const dis = isAdmin ? '' : 'disabled';
    const chan = (key, name, field, ph, extra = '') => `<div class="ch">
      <div class="ch-head"><div>${name}<small>${extra}</small></div>
        <button type="button" class="switch" role="switch" aria-checked="${state.notifyDraft?.[key + '_enabled'] ?? n[key + '_enabled']}" aria-label="启用 ${name}" data-act="toggleCh" data-key="${key}" ${dis}></button></div>
      <input class="input" id="n-${key}" value="${esc(n[field])}" placeholder="${ph}" ${dis}></div>`;
    return `
    <div class="head"><div><h1>设置</h1><p>负面内容命中后推送到已启用的渠道；同一相似内容 6 小时内只推送一次。</p></div></div>
    ${systemBanner()}
    <div class="settings">
      <form class="card" id="notifyForm">
        <h3>预警推送渠道</h3>
        ${!isAdmin ? '<div class="readonly-note">只有管理员可以修改推送设置。</div>' : ''}
        ${chan('wecom', '企业微信群机器人', 'wecom_webhook', 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=…')}
        ${chan('feishu', '飞书群机器人', 'feishu_webhook', 'https://open.feishu.cn/open-apis/bot/v2/hook/…')}
        ${chan('email', '邮件', 'email_to', '多个邮箱用逗号分隔', n.email_configured ? '' : ' · 服务器未配置 SMTP，暂不可用')}
        <div class="ch"><div class="ch-head"><div>免打扰时段<small> · 期间的预警结束后合并推送</small></div>
          <button type="button" class="switch" role="switch" aria-checked="${state.notifyDraft?.quiet_enabled ?? n.quiet_enabled}" aria-label="启用免打扰" data-act="toggleCh" data-key="quiet" ${dis}></button></div>
          <div class="time-row"><input class="input" type="time" id="qStart" value="${esc(n.quiet_start)}" aria-label="开始" ${dis}><span>至</span><input class="input" type="time" id="qEnd" value="${esc(n.quiet_end)}" aria-label="结束" ${dis}></div></div>
        <div class="ch"><div class="ch-head"><div>负面预警阈值<small> · 模型置信度达到该值才推送</small></div></div>
          <div class="time-row"><input class="input" type="number" id="nThr" min="0" max="1" step="0.05" value="${n.neg_threshold}" ${dis}></div></div>
        ${isAdmin ? `<div class="inline-actions"><button class="btn primary">保存</button><button type="button" class="btn" data-act="testPush">发送测试预警</button><span class="result" id="pushResult"></span></div>` : ''}
      </form>
      <div class="card"><h3>成员 <span class="quota" style="margin-left:auto">${state.users.length} 人</span></h3>
        <div class="list" style="margin-top:8px">${state.users.map(u => `<div class="item"><span class="avatar">${esc(u.name[0])}</span><div style="min-width:0">${esc(u.name)}<small>${esc(u.phone)}</small></div>
          <span class="pill ${u.role === 'admin' ? 'kw' : 'neu'}" style="margin-left:auto">${u.role === 'admin' ? '管理员' : '成员'}</span>
          ${isAdmin && u.id !== state.user.id ? `<button class="link danger" data-act="delUser" data-id="${u.id}">${state.confirmUser === u.id ? '确认移除？' : '移除'}</button>` : ''}</div>`).join('')}</div>
        ${isAdmin ? `<form class="form-grid" id="invite" style="margin-top:12px"><div class="time-row"><input class="input" id="invName" placeholder="姓名" maxlength="20" style="width:100px"><input class="input grow" id="invPhone" inputmode="tel" maxlength="11" placeholder="手机号" style="width:auto;flex:1"><button class="btn primary">邀请</button></div></form>` : ''}
      </div>
      <div class="card"><h3>数据源</h3>
        <div class="list" style="margin-top:8px">
          <div class="item"><div>采集状态<small>${esc(sys.message || '—')}</small></div></div>
          <div class="item"><div>数据源<small>${sys.crawler_mode === 'tikhub' ? 'TikHub 小红书搜索接口' : '演示数据（未配置 TIKHUB_API_KEY）'}</small></div></div>
          <div class="item"><div>情感判断<small>${sys.sentiment_mode === 'llm' ? 'DeepSeek 大模型' : '本地规则（未配置 LLM_API_KEY）'}</small></div></div>
          <div class="item"><div>监测词<small>${sys.keyword_count ?? 0} 个 · 每 ${sys.interval_min ?? 10} 分钟一轮 · 最近成功 ${sys.last_success_at ? fmtTime(sys.last_success_at) : '—'}</small></div></div>
        </div>
        ${isAdmin ? `<div class="inline-actions" style="margin-top:12px"><button class="btn" data-act="crawlNow">立即采集一轮</button>${sys.state === 'auth_failed' || sys.state === 'paused' ? '<button class="btn" data-act="resume">恢复采集</button>' : ''}</div>` : ''}
      </div>
    </div>`;
  }

  // ---------- 预警详情 ----------
  async function showAlert(id) {
    try {
      const a = await api('/alerts/' + id);
      const p = a.hit.post;
      const ch = { wecom: '企业微信', feishu: '飞书', email: '邮件' };
      $('#layer').innerHTML = `<div class="overlay" data-close="1"><div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dlgT">
        <h2 id="dlgT">预警详情</h2><p class="hint">${a.status === 'queued' ? '免打扰期间，排队中' : '生成于 ' + fmtTime(a.created_at)}</p>
        <div class="im"><span class="t">【负面预警】${esc(a.hit.group.name)} · 小红书</span>
          <span>作者：${esc(p.author_name)}</span><span>摘录：${esc((p.title || p.content).slice(0, 40))}</span>
          <span>互动：赞 ${fmtNum(p.like)} · 评 ${fmtNum(p.comment)} · 藏 ${fmtNum(p.collect)}</span>
          <span><a href="${esc(p.url)}" target="_blank" rel="noopener">查看原文</a></span></div>
        <div class="deliv">${a.deliveries.length ? a.deliveries.map(d => `<span>${ch[d.channel] || d.channel}：${d.status === 'ok' ? '已送达 ' + fmtTime(d.sent_at) : '失败（' + esc(d.error || '') + '）'}</span>`).join('') : '<span>没有已启用的推送渠道，未发送。</span>'}</div>
        <div class="end inline-actions" style="justify-content:space-between">
          <div class="inline-actions"><span class="result">这条预警有用吗？</span>
            <button class="btn ${a.feedback === 'valid' ? 'primary' : ''}" data-act="feedback" data-id="${a.id}" data-v="valid">有效</button>
            <button class="btn ${a.feedback === 'invalid' ? 'primary' : ''}" data-act="feedback" data-id="${a.id}" data-v="invalid">无效</button></div>
          <button class="btn" data-close="1">关闭</button></div></div></div>`;
    } catch (e) { fail(e); }
  }

  // ---------- 渲染 ----------
  function render() {
    if (!state.user) { $('#root').innerHTML = renderLogin(); return; }
    const body = state.page === 'feed' ? renderFeed() : state.page === 'keywords' ? renderKeywords() : renderSettings();
    const active = document.activeElement?.id;
    const pos = active === 'fQ' ? $('#fQ').selectionStart : null;
    $('#root').innerHTML = shell(body);
    if (active === 'fQ') { const q = $('#fQ'); q.focus(); q.setSelectionRange(pos, pos); }
  }

  function updateHit(h) {
    const i = state.hits.findIndex(x => x.id === h.id);
    if (i >= 0) state.hits[i] = h;
  }

  // ---------- 事件 ----------
  let qTimer = null;
  document.addEventListener('input', e => {
    if (e.target.id === 'fQ') {
      state.f.q = e.target.value.trim();
      clearTimeout(qTimer);
      qTimer = setTimeout(() => loadHits().then(render).catch(fail), 300);
    }
  });

  document.addEventListener('change', async e => {
    const t = e.target;
    if (t.id === 'fGroup') { state.f.group = t.value; await loadHits().catch(fail); render(); }
    if (t.dataset.act === 'sent') {
      try { updateHit(await api('/hits/' + t.dataset.id, { method: 'PATCH', body: { sentiment_manual: t.value } })); toast('情感已修正，将用作模型示例'); await loadSummary(); } catch (err) { fail(err); }
      render();
    }
  });

  document.addEventListener('click', async e => {
    if (e.target.dataset?.close) { $('#layer').innerHTML = ''; return; }
    const nav = e.target.closest('[data-page]');
    if (nav) { go(nav.dataset.page); return; }
    const sg = e.target.closest('[data-seg]');
    if (sg) { state.f[sg.dataset.seg] = sg.dataset.v; render(); await loadHits().catch(fail); render(); return; }
    if (e.target.id === 'sendCode') return sendCode(e.target);
    const a = e.target.closest('[data-act]');
    if (!a) return;
    const id = a.dataset.id, act = a.dataset.act;
    try {
      if (act === 'logout') { await api('/auth/logout', { method: 'POST' }); state.user = null; render(); return; }
      if (act === 'refresh') { await Promise.all([loadHits(), loadSummary()]); }
      if (act === 'more') { await loadHits(false); }
      if (act === 'alert') return showAlert(id);
      if (act === 'feedback') { await api('/alerts/' + id, { method: 'PATCH', body: { feedback: a.dataset.v } }); toast('感谢反馈'); return showAlert(id); }
      if (act === 'irrelevant') {
        await api('/hits/' + id, { method: 'PATCH', body: { is_irrelevant: true } });
        state.hits = state.hits.filter(h => String(h.id) !== id); toast('已标记为不相关'); await loadSummary();
      }
      if (act === 'done') {
        const next = a.dataset.status === 'done' ? 'open' : 'done';
        const h = await api('/hits/' + id, { method: 'PATCH', body: { status: next } });
        if (state.f.status !== 'all') state.hits = state.hits.filter(x => x.id !== h.id); else updateHit(h);
        toast(next === 'done' ? '已标记为已处理' : '已恢复为待处理'); await loadSummary();
      }
      if (act === 'toggleGroup') {
        const g = state.groups.find(x => String(x.id) === id);
        await api('/keyword-groups/' + id, { method: 'PUT', body: { enabled: !g.enabled } });
        toast(g.enabled ? `已停用「${g.name}」` : `已启用「${g.name}」`); await loadGroups();
      }
      if (act === 'editGroup') { state.editing = Number(id); }
      if (act === 'cancelEdit') { state.editing = null; }
      if (act === 'delGroup') {
        if (state.confirmDel !== Number(id)) { state.confirmDel = Number(id); render(); return; }
        await api('/keyword-groups/' + id, { method: 'DELETE' }); state.confirmDel = null; toast('已删除'); await loadGroups();
      }
      if (act === 'delUser') {
        if (state.confirmUser !== Number(id)) { state.confirmUser = Number(id); render(); return; }
        await api('/users/' + id, { method: 'DELETE' }); state.confirmUser = null; toast('已移除'); await loadSettings();
      }
      if (act === 'toggleCh') {
        const key = a.dataset.key + '_enabled';
        a.setAttribute('aria-checked', String(a.getAttribute('aria-checked') !== 'true'));
        state.notifyDraft = { ...(state.notifyDraft || {}), [key]: a.getAttribute('aria-checked') === 'true' };
        return;
      }
      if (act === 'testPush') {
        const r = (await api('/settings/notify/test', { method: 'POST' })).result;
        const names = { wecom: '企业微信', feishu: '飞书', email: '邮件', _: '' };
        const txt = Object.entries(r).map(([k, v]) => `${names[k] ? names[k] + '：' : ''}${v === 'ok' ? '成功' : v}`).join('；');
        const el = $('#pushResult'); el.textContent = txt; el.className = 'result ' + (Object.values(r).every(v => v === 'ok') ? 'ok' : 'bad');
        return;
      }
      if (act === 'crawlNow') { await api('/system/crawl-now', { method: 'POST' }); toast('已开始采集，稍后刷新查看'); }
      if (act === 'resume') { await api('/system/crawler/resume', { method: 'POST' }); toast('已恢复采集'); await loadSummary(); }
    } catch (err) { fail(err); }
    render();
  });

  async function sendCode(btn) {
    const phone = $('#lgPhone').value.trim();
    $('#lgErr').textContent = '';
    if (!/^1\d{10}$/.test(phone)) { $('#lgErr').textContent = '请输入 11 位手机号'; return; }
    try {
      const r = await api('/auth/sms-code', { method: 'POST', body: { phone }, allow401: true });
      if (r.dev_code) { $('#lgCode').value = r.dev_code; toast('开发环境：验证码已自动填入'); } else toast('验证码已发送');
      let n = 60; btn.disabled = true;
      const t = setInterval(() => { btn.textContent = `${--n} 秒后重发`; if (n <= 0) { clearInterval(t); btn.disabled = false; btn.textContent = '获取验证码'; } }, 1000);
    } catch (e) { $('#lgErr').textContent = e.message; }
  }

  const splitWords = v => v.split(/[,，\n]/).map(s => s.trim()).filter(Boolean);

  document.addEventListener('submit', async e => {
    e.preventDefault();
    const f = e.target;
    try {
      if (f.id === 'loginForm') {
        const r = await api('/auth/login', { method: 'POST', body: { phone: $('#lgPhone').value.trim(), code: $('#lgCode').value.trim() }, allow401: true });
        state.user = r.user; return go(state.page);
      }
      if (f.id === 'groupForm') {
        const body = { name: $('#ngName').value.trim(), words: splitWords($('#ngWords').value), exclude_words: splitWords($('#ngEx').value) };
        if (!body.name || !body.words.length) { $('#ngErr').textContent = '请填写名称和至少一个监测词。'; return; }
        if (body.words.length > state.limits.max_words) { $('#ngErr').textContent = `每组最多 ${state.limits.max_words} 个监测词。`; return; }
        if (state.editing) { await api('/keyword-groups/' + state.editing, { method: 'PUT', body }); toast('已保存，正在用新关键词回溯近 3 天'); state.editing = null; }
        else { await api('/keyword-groups', { method: 'POST', body: { ...body, platforms: ['xhs'] } }); toast(`「${body.name}」已开始监测，正在回溯近 3 天`); }
        await loadGroups(); render(); return;
      }
      if (f.id === 'notifyForm') {
        const sw = k => document.querySelector(`[data-act="toggleCh"][data-key="${k}"]`).getAttribute('aria-checked') === 'true';
        const body = {
          wecom_enabled: sw('wecom'), wecom_webhook: $('#n-wecom').value.trim(),
          feishu_enabled: sw('feishu'), feishu_webhook: $('#n-feishu').value.trim(),
          email_enabled: sw('email'), email_to: $('#n-email').value.trim(),
          quiet_enabled: sw('quiet'), quiet_start: $('#qStart').value, quiet_end: $('#qEnd').value,
          neg_threshold: Number($('#nThr').value),
        };
        state.notify = await api('/settings/notify', { method: 'PUT', body }); state.notifyDraft = null;
        toast('推送设置已保存'); render(); return;
      }
      if (f.id === 'invite') {
        const phone = $('#invPhone').value.trim();
        if (!/^1\d{10}$/.test(phone)) { toast('请输入 11 位手机号'); return; }
        await api('/users', { method: 'POST', body: { phone, name: $('#invName').value.trim() || '新成员' } });
        toast('已添加成员，对方用该手机号即可登录'); await loadSettings(); render();
      }
    } catch (err) {
      if (f.id === 'loginForm') $('#lgErr').textContent = err.message;
      else if (f.id === 'groupForm') $('#ngErr').textContent = err.message;
      else fail(err);
    }
  });

  document.addEventListener('keydown', e => { if (e.key === 'Escape') $('#layer').innerHTML = ''; });

  // 每分钟检查一次新内容和概况
  setInterval(async () => {
    if (!state.user || document.hidden) return;
    try {
      await loadSummary();
      if (state.page === 'feed') {
        const d = await api('/hits?' + hitsQuery({ limit: 1 }));
        const top = state.hits[0]?.id || 0;
        state.newCount = d.items[0] && d.items[0].id > top ? 1 : 0;
      }
      // 只在信息流页自动重绘，避免冲掉设置页里正在编辑的内容
      if (state.page === 'feed' && !['SELECT', 'INPUT'].includes(document.activeElement?.tagName)) render();
    } catch (e) {}
  }, 60000);

  // ---------- 启动 ----------
  (async () => {
    const m = location.hash.match(/^#hit-(\d+)$/);
    if (m) { state.page = 'feed'; state.f.status = 'all'; state.flashId = Number(m[1]); }
    try { state.user = (await api('/auth/me', { allow401: true })).user; } catch (e) { state.user = null; }
    if (state.user) go(state.page); else render();
  })();
})();
