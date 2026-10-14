import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, type Home as HomeData } from "../lib/api";
import { audio } from "../lib/audio";
import { flushFinishes, flushPending } from "../lib/offline";
import { useLongPress } from "../lib/useLongPress";

// 孩子端首页：零文字，只有图标、颜色和语音（PRD F12）
export default function Home() {
  const nav = useNavigate();
  const [data, setData] = useState<HomeData | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    flushFinishes().then(() => flushPending());
    api.home().then(setData).catch(() => setOffline(true));
  }, []);

  const parent = useLongPress(() => nav("/parent"), 3000);

  const go = (path: string) => {
    audio.unlock();
    nav(path);
  };

  const sayNoShow = () => {
    audio.unlock();
    if (data) {
      audio.register(data.voices);
      audio.play(["sys:ask_parent"]);
    }
  };

  const ep = data?.episode;
  return (
    <div className="child-screen home" style={{ ["--theme" as string]: ep?.theme_color ?? "#F7A1C4" }}>
      <button className="corner-btn right" aria-label="parent" {...parent.bind}>
        <span className={parent.pressing ? "hold-ring active" : "hold-ring"} />⚙️
      </button>
      <button className="corner-btn left" aria-label="stickers" onClick={() => go("/stickers")}>
        📒{data && data.sticker_count > 0 && <span className="badge-dot" />}
      </button>

      {ep ? (
        <div className="home-main">
          <div className="show-card" aria-label="today">📺</div>
          <div className="big-buttons">
            <button className="big-btn before" aria-label="preview" onClick={() => go(`/play/${ep.id}/preview`)}>
              <span className="big-icon">🔭</span>
              {ep.preview_done && <span className="done-star">⭐</span>}
            </button>
            <button className="big-btn after" aria-label="review" onClick={() => go(`/play/${ep.id}/review`)}>
              <span className="big-icon">🎁</span>
              {ep.review_done && <span className="done-star">⭐</span>}
            </button>
          </div>
        </div>
      ) : (
        <div className="home-main">
          <button className="waiting" aria-label="no show" onClick={sayNoShow}>
            {offline ? "📡" : "😴"}
          </button>
        </div>
      )}

      {data?.spaced_available && (
        <button className="mini-review" aria-label="mini review" onClick={() => go("/play/spaced/spaced")}>
          🔁
        </button>
      )}
    </div>
  );
}
