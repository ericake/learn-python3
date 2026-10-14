import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, type Episode } from "../lib/api";

export const STATUS_LABEL: Record<Episode["status"], string> = {
  draft: "草稿", extracting: "选词中", reviewing: "待审核", generating: "生成中", ready: "已就绪", failed: "失败",
};

export default function EpisodeList() {
  const nav = useNavigate();
  const [list, setList] = useState<Episode[] | null>(null);
  const [show, setShow] = useState("Peppa Pig");
  const [season, setSeason] = useState("1");
  const [epNo, setEpNo] = useState("1");
  const [title, setTitle] = useState("Muddy Puddles");
  const [error, setError] = useState("");

  useEffect(() => {
    api.episodes().then(setList).catch((e) => setError(String(e.message)));
  }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const ep = await api.createEpisode({
        show_name: show.trim(), title: title.trim() || null,
        season: season ? Number(season) : null, episode_no: epNo ? Number(epNo) : null,
      });
      nav(`/parent/episodes/${ep.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="stack">
      <form className="panel" onSubmit={create}>
        <h2>新建剧集</h2>
        <div className="grid4">
          <label>动画名称<input required value={show} onChange={(e) => setShow(e.target.value)} list="shows" /></label>
          <label>季<input inputMode="numeric" value={season} onChange={(e) => setSeason(e.target.value)} /></label>
          <label>集<input inputMode="numeric" value={epNo} onChange={(e) => setEpNo(e.target.value)} /></label>
          <label>标题<input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
        </div>
        <datalist id="shows">
          {[...new Set((list ?? []).map((e) => e.show_name))].map((s) => <option key={s} value={s} />)}
        </datalist>
        <button className="primary" type="submit">创建并输入台词</button>
        {error && <p className="error">{error}</p>}
      </form>

      <section className="panel">
        <h2>剧集列表</h2>
        {list === null ? <p>加载中…</p> : list.length === 0 ? <p className="muted">还没有剧集</p> : (
          <table>
            <thead><tr><th>计划日期</th><th>剧集</th><th>条目</th><th>状态</th></tr></thead>
            <tbody>
              {list.map((e) => (
                <tr key={e.id}>
                  <td>{e.planned_date}</td>
                  <td><Link to={`/parent/episodes/${e.id}`}>{e.show_name}
                    {e.season != null && ` S${e.season}`}{e.episode_no != null && `E${e.episode_no}`}
                    {e.title && ` · ${e.title}`}</Link></td>
                  <td>{e.selected_count || "—"}</td>
                  <td><span className={`tag ${e.status}`}>{STATUS_LABEL[e.status]}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
