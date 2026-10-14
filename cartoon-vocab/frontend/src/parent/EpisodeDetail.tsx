import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, type Episode, type EpisodeItem } from "../lib/api";
import { STATUS_LABEL } from "./EpisodeList";

const TYPE_LABEL: Record<string, string> = { noun: "名词", verb: "动词", adj: "形容词", phrase: "短语", other: "其他" };

function listen(url: string | null, text: string | null, accentRate = 1) {
  if (url) {
    new Audio(url).play().catch(() => undefined);
  } else if (text && window.speechSynthesis) {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-GB";
    u.rate = accentRate;
    window.speechSynthesis.speak(u);
  }
}

export default function EpisodeDetail() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const [ep, setEp] = useState<Episode | null>(null);
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [newItem, setNewItem] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const poll = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const e = await api.episode(id);
      setEp(e);
      return e;
    } catch (err) {
      setError((err as Error).message);
      return null;
    }
  }, [id]);

  useEffect(() => {
    load();
    return () => {
      if (poll.current) window.clearInterval(poll.current);
    };
  }, [load]);

  // 后台任务进行中时轮询进度
  useEffect(() => {
    if (!ep) return;
    const working = ep.status === "extracting" || ep.status === "generating";
    if (working && !poll.current) {
      poll.current = window.setInterval(load, 1000);
    } else if (!working && poll.current) {
      window.clearInterval(poll.current);
      poll.current = null;
    }
  }, [ep, load]);

  const run = async (fn: () => Promise<unknown>) => {
    setError("");
    setBusy(true);
    try {
      await fn();
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!ep) return <p>{error || "加载中…"}</p>;

  const items = ep.items ?? [];
  const selected = items.filter((i) => i.selected);
  const backups = items.filter((i) => !i.selected);
  const working = ep.status === "extracting" || ep.status === "generating";
  const reviewable = ep.status === "reviewing" || ep.status === "failed" || ep.status === "ready";

  const updateItem = (item: EpisodeItem, patch: Partial<EpisodeItem>) =>
    run(() => api.patchItem(ep.id, item.id, patch));

  return (
    <div className="stack">
      <section className="panel">
        <div className="row spread">
          <h2>
            {ep.show_name}
            {ep.season != null && ` S${ep.season}`}{ep.episode_no != null && `E${ep.episode_no}`}
            {ep.title && ` · ${ep.title}`}
          </h2>
          <span className={`tag ${ep.status}`}>{STATUS_LABEL[ep.status]}</span>
        </div>
        {working && (
          <div className="progressbar">
            <div style={{ width: ep.progress.total ? `${(100 * (ep.progress.done ?? 0)) / ep.progress.total}%` : "30%" }} />
            <span>{ep.status === "extracting" ? "正在分析台词、挑选重点词…" : `正在生成图片和发音 ${ep.progress.done ?? 0}/${ep.progress.total ?? "?"}`}</span>
          </div>
        )}
        {ep.error && <p className="error">{ep.error}</p>}
        {ep.progress.extractor === "offline" && ep.status === "reviewing" && (
          <p className="muted">提示：未配置 Claude 密钥，本次使用离线规则选词。</p>
        )}
        {ep.status === "ready" && (
          <p className="ok">课程已就绪，孩子端首页可以开始“看前 / 看后”了。<Link to={`/parent/reports?episode=${ep.id}`}>查看本集报告</Link></p>
        )}
      </section>

      {!working && (
        <details className="panel" open={!ep.has_transcript}>
          <summary><h2>{ep.has_transcript ? `台词（${ep.sentence_count} 句）· 重新提交` : "输入台词"}</h2></summary>
          <textarea rows={10} placeholder="粘贴整集英文台词，支持带时间轴的 SRT / VTT 字幕内容" value={text}
                    onChange={(e) => setText(e.target.value)} />
          <div className="row">
            <input type="file" accept=".txt,.srt,.vtt,text/plain" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <button className="primary" disabled={busy || (!text.trim() && !file)}
                    onClick={() => run(() => api.submitTranscript(ep.id, text, file))}>
              {ep.has_transcript ? "重新选词" : "提交并自动选词"}
            </button>
          </div>
          {ep.has_transcript && <p className="muted">重新提交会清空当前词表。</p>}
        </details>
      )}

      {reviewable && items.length > 0 && (
        <section className="panel">
          <div className="row spread">
            <h2>重点词与短语（已选 {selected.length} 个，建议 {ep.target_item_count} 个）</h2>
            <button className="primary" disabled={busy || selected.length < 4 || selected.length > 12}
                    onClick={() => run(() => api.confirm(ep.id))}>
              {ep.status === "ready" ? "重新生成素材" : ep.status === "failed" ? "重试生成" : "确认并生成课程"}
            </button>
          </div>
          <div className="cards">
            {selected.map((it) => (
              <ItemCard key={it.id} item={it} busy={busy} onToggle={() => updateItem(it, { selected: false })}
                        onSave={(p) => updateItem(it, p)}
                        onRegen={() => run(() => api.regenerateImage(ep.id, it.id))}
                        onUpload={(f) => run(() => api.uploadImage(ep.id, it.id, f))} />
            ))}
          </div>
          <form className="row" onSubmit={(e) => { e.preventDefault(); run(() => api.addItem(ep.id, newItem)).then(() => setNewItem("")); }}>
            <input placeholder="手动添加词或短语，如 umbrella / put on" value={newItem} onChange={(e) => setNewItem(e.target.value)} />
            <button disabled={busy || !newItem.trim()}>添加</button>
          </form>
          {backups.length > 0 && (
            <>
              <h3>备选（点击加入）</h3>
              <div className="chips">
                {backups.map((b) => (
                  <button key={b.id} className="chip" disabled={busy} onClick={() => updateItem(b, { selected: true })}
                          title={b.reason}>
                    {b.emoji} {b.text} <small>{b.meaning_zh}</small>
                  </button>
                ))}
              </div>
            </>
          )}
        </section>
      )}
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button className="ghost danger" onClick={() => {
          if (confirm("确定删除这一集？学习记录会保留在词汇报告中。")) run(() => api.deleteEpisode(ep.id)).then(() => nav("/parent"));
        }}>删除剧集</button>
      </div>
    </div>
  );
}

function ItemCard({ item, busy, onToggle, onSave, onRegen, onUpload }: {
  item: EpisodeItem; busy: boolean; onToggle: () => void; onSave: (p: Partial<EpisodeItem>) => void;
  onRegen: () => void; onUpload: (f: File) => void;
}) {
  const [sentence, setSentence] = useState(item.source_sentence);
  const [meaning, setMeaning] = useState(item.meaning_zh);
  const dirty = sentence !== item.source_sentence || meaning !== item.meaning_zh;
  return (
    <div className={`item-card ${item.asset_error ? "has-error" : ""}`}>
      <div className="thumb">
        {item.image_url ? <img src={item.image_url} alt={item.text} /> : <span className="emoji">{item.emoji ?? "⭐"}</span>}
      </div>
      <div className="body">
        <div className="row spread">
          <strong className="word">{item.text}</strong>
          <span className="tag">{TYPE_LABEL[item.type] ?? item.type}</span>
        </div>
        <input className="inline" value={meaning} placeholder="中文释义" onChange={(e) => setMeaning(e.target.value)} />
        <textarea className="inline" rows={2} value={sentence} onChange={(e) => setSentence(e.target.value)} />
        <p className="muted small">{item.reason}</p>
        {item.asset_error && <p className="error small">素材失败：{item.asset_error}</p>}
        <div className="row wrap">
          {dirty && <button disabled={busy} onClick={() => onSave({ source_sentence: sentence, meaning_zh: meaning })}>保存</button>}
          {(item.audio_normal_url || item.speak_text) && (
            <>
              <button className="ghost" onClick={() => listen(item.audio_normal_url, item.speak_text)}>🔊 读音</button>
              <button className="ghost" onClick={() => listen(item.audio_slow_url, item.speak_text, 0.7)}>🐢 慢速</button>
              <button className="ghost" onClick={() => listen(item.sentence_audio_url, item.source_sentence)}>💬 原句</button>
            </>
          )}
          {item.image_url && (
            <button className="ghost" disabled={busy || item.image_regen_left <= 0} onClick={onRegen}>
              换一张（剩 {item.image_regen_left}）
            </button>
          )}
          {item.image_url && (
            <label className="ghost file-btn">上传图片
              <input type="file" accept="image/png,image/jpeg,image/webp" hidden
                     onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])} />
            </label>
          )}
          <button className="ghost danger" disabled={busy} onClick={onToggle}>移除</button>
        </div>
      </div>
    </div>
  );
}
