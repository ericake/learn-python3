import { BrowserRouter, Route, Routes } from "react-router-dom";

import Home from "./child/Home";
import Player from "./child/Player";
import StickerBook from "./child/StickerBook";
import EpisodeDetail from "./parent/EpisodeDetail";
import EpisodeList from "./parent/EpisodeList";
import ParentLayout from "./parent/ParentLayout";
import Reports from "./parent/Reports";
import Settings from "./parent/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/play/:episodeId/:mode" element={<Player />} />
        <Route path="/stickers" element={<StickerBook />} />
        <Route path="/parent" element={<ParentLayout />}>
          <Route index element={<EpisodeList />} />
          <Route path="episodes/:id" element={<EpisodeDetail />} />
          <Route path="reports" element={<Reports />} />
          <Route path="settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Home />} />
      </Routes>
    </BrowserRouter>
  );
}
