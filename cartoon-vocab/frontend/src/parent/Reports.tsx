import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api, type Episode, type EpisodeReport, type ReportSummary, type WordEntry } from "../lib/api";

export default function Reports() {
  const [params, setParams] = useSearchParams();
  const [summary, setSummary] = useState<ReportSummary | null>(null);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [report, setReport] = useState<EpisodeReport | null>(null);
  const [msg, setMsg] = useState("");
  const epId = params.get("episode") ?? "";

  useEffect(() => {
    api.reportSummary().then(setSummary);
    api.episodes().then((l) => setEpisodes(l.filter((e) => e.status === "ready")));
  }, []);
  useEffect(() => {
    if (epId) api.reportEpisode(epId).then(setReport).catch(() => setReport(null));
    else setReport(null);
  }, [epId]);

  const toTomorrow = async (w: WordEntry) => {
    await api.weakToTomorrow(w.vocab_id);
    setMsg(`“${w.text}” 已加入明日复习`);
  };

  return (
    <div className="stack">
      {summary && (
        <section className="panel">
          <h2>总览</h2>
          <div className="stats">
            <div><b>{summary.streak_days}</b><span>连续学习天数</span></div>
            <div><b>{summary.days_this_week}</b><span>近 7 天学习天数</span></div>
            <div><b>{summary.counts.mastered}</b><span>已掌握</span></div>
            <div><b>{summary.counts.learning}</b><span>学习中</span></div>
            <div><b>{summary.counts.weak}</b><span>薄弱</span></div>
          </div>
          {summary.weak.length > 0 && (
            <>
              <h3>薄弱词</h3>
              <div className="chips">
                {summary.weak.map((w) => (
                  <button key={w.vocab_id} className="chip warn" onClick={() => toTomorrow(w)}>
                    {w.emoji} {w.text} · 错 {w.wrong_count} 次 · 加入明日复习
                  </button>
                ))}
              </div>
            </>
          )}
          {msg && <p className="ok">{msg}</p>}
          <WordGroup title="学习中" list={summary.learning} />
          <WordGroup title="已掌握" list={summary.mastered} />
        </section>
      )}

      <section className="panel">
        <div className="row spread">
          <h2>单集报告</h2>
          <select value={epId} onChange={(e) => setParams(e.target.value ? { episode: e.target.value } : {})}>
            <option value="">选择剧集</option>
            {episodes.map((e) => (
              <option key={e.id} value={e.id}>{e.planned_date} · {e.show_name} {e.title ?? ""}</option>
            ))}
          </select>
        </div>
        {report && (
          <>
            <p>
              预习：{report.preview.done ? `✅ 用时 ${Math.round((report.preview.duration_sec ?? 0) / 60)} 分钟` : "未完成"}
              ；复习：{report.review.done ? `✅ 用时 ${Math.round((report.review.duration_sec ?? 0) / 60)} 分钟` : "未完成"}
            </p>
            <table>
              <thead><tr><th>条目</th><th>首次选择正确</th></tr></thead>
              <tbody>
                {report.items.map((i) => (
                  <tr key={i.vocab_id}>
                    <td>{i.emoji} {i.text}</td>
                    <td>{i.first_try_total ? `${i.first_try_correct}/${i.first_try_total}` : "—"}
                      {i.first_try_total > 0 && i.first_try_correct < i.first_try_total && " ⚠️"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>
    </div>
  );
}

function WordGroup({ title, list }: { title: string; list: WordEntry[] }) {
  if (!list.length) return null;
  return (
    <>
      <h3>{title}（{list.length}）</h3>
      <div className="chips">{list.map((w) => <span key={w.vocab_id} className="chip static">{w.emoji} {w.text}</span>)}</div>
    </>
  );
}
