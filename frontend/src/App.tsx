// アプリの骨組み（石川）: 認証ゲート + ルーティング。
// 画面遷移は React Router v7 が担い、各ページが job の status から表示を導出する。
// 設計根拠: design_review_and_frontback.md §6.2, §6.3 / Issue #8

import { Route, Routes } from "react-router-dom";
import { AuthGate } from "./components/AuthGate";
import { HomePage } from "./pages/HomePage";
import { JobPage } from "./pages/JobPage";
import "./App.css";

export default function App() {
  return (
    <AuthGate>
      <header className="app-header">
        <h1>SpeakScore</h1>
        <p className="tagline">運に頼らず、実力で内定を掴む</p>
      </header>

      <main className="app-main">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/jobs/:jobId" element={<JobPage />} />
        </Routes>
      </main>
    </AuthGate>
  );
}
