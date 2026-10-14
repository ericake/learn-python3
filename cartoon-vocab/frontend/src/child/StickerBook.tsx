import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../lib/api";
import { stickerEmoji } from "../lib/stickers";

export default function StickerBook() {
  const nav = useNavigate();
  const [list, setList] = useState<{ sticker_key: string }[]>([]);
  useEffect(() => {
    api.stickers().then(setList).catch(() => setList([]));
  }, []);
  const slots = Math.max(12, Math.ceil((list.length + 1) / 6) * 6);
  return (
    <div className="child-screen stickers">
      <button className="corner-btn left" aria-label="home" onClick={() => nav("/")}>🏠</button>
      <div className="sticker-grid">
        {Array.from({ length: slots }, (_, i) => (
          <div key={i} className={i < list.length ? "sticker got" : "sticker"}>
            {i < list.length ? stickerEmoji(list[i].sticker_key) : ""}
          </div>
        ))}
      </div>
    </div>
  );
}
