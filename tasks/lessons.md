# Lessons

## 2026-09-24：唯讀盤點的 repository 初始化
- 類別：對 repo 介面的錯誤假設。
- 失敗與訊號：直接呼叫 `EpisodeSourceRepository()`，收到缺少四個必要參數的 TypeError；未修改資料。
- 預防：先閱讀建構子或既有呼叫點；盤點時沿用 `EpisodeNoteSynthesizer().source_repository` 的既定路徑配置。

## 2026-09-24：使用者指定來源替代方案
- 類別：需求理解。使用者要求缺集改以影片語音轉錄。
- 規則：第三方逐字稿未釋出不等於官方內容不可取得；使用者授權 ASR 時採獨立來源標示與可追溯證據，避免仍以原先三方對齊政策阻擋。
- 檢查：確認新筆記與封存標記 ASR，且不虛構第三方來源。

## 2026-09-24：ASR 缺標點造成合成失真
- 類別：對外部文字格式的錯誤假設。
- 訊號：EP694 dry-run 僅有 4 章且集中開場廣告；清理程序將無標點辨識行合併成超長句，抽取器略過正文。
- 預防：ASR 專用分段，使用已確認的 content_start_line 排除開場業配；回歸測試涵蓋後段內容，冷封存與原始 ASR JSON 不受合成前處理影響。

## 2026-09-26：技能驗收須核對描述成本與引用檔案
- 類別：缺少驗證。盤點舊 issues 發現描述超過約 30-token 目標，引用範例 EP690.md 缺少四位數補零且使用 file://。
- 預防：以 tokenizer 實測 frontmatter description；引用範例先檢查實際檔案存在，並採介面支援的 Markdown 路徑。
- Tripwire：搜尋 `file://` 與 `episodes/EP690.md`，用 pathlib 檢查 EP0690.md 存在。

## 2026-09-26：Preview 不產生 Publication 索引
- 類別：對 repo 行為的錯誤假設。全集合成成功，但驗證腳本錯誤要求 Preview 有 _index.md/README.md 而失敗。
- 預防：先讀 `test_synthesize_preview_writes_only_episode_files`；索引驗收改用隔離 publish + verify，不改動既有分層。
