# 系統規格書：跨集數主題式深度知識庫指南與產業鏈專題合成系統 (Cross-Episode Thematic Topic Guides & Domain Synthesis)

## Problem Statement

使用者與 AI Agent 雖然已擁有全面生成且零瑕疵的 689 集雙層結構化筆記（含 5,299 個章節與核心觀點），但在查詢宏觀跨集數主題（例如「ASIC 與 CSP 自研晶片演進版圖」、「AI 伺服器散熱與 800V 高壓供電技術迭代」、「主委部位管理、停損紀律與期望值實戰守則」）時，面臨以下限制與痛點：
1. **單集孤島效應**：現有筆記以單集（`EPxxxx.md`）為邊界，使用者必須自行在 689 個檔案間手動過濾、拼湊與對照多年（2020–2026）的觀點演變，缺乏跨集數的主題聚類與時間軸脈絡梳理。
2. **缺乏主題級深度導讀手冊**：針對高頻關注的關鍵產業鏈與投資心態哲學，缺少權威、系統化且開箱即用的「領域專題指南 (Topic Guide)」，無法讓使用者在 3 分鐘內通盤掌握該主題在股癌全集中的核心脈絡。
3. **Agent 跨集檢索開銷過大**：當 Agent 接收到廣泛主題提問時，若缺乏主題級聚合索引，需逐一檢索數十篇單集筆記並自行合成，大幅增加 Token 消耗與幻覺風險。
4. **缺乏主題合成品質閘門與接地保證**：若直接透過未受約束的 LLM 生成主題總結，容易出現年份錯置、未接地虛構觀點或漏掉關鍵集數論點的問題。

## Solution

建立**跨集數主題式深度知識庫指南與產業鏈專題合成系統**，基於已驗證的 5,299 個章節結構與觀點資料，提供確定性主題聚類、時間軸演進梳理、標準化專題指南渲染與整合 CLI 工具：
1. **領域主題資料模型 (Thematic Domain Model)**：定義結構化領域物件（`TopicDefinition`、`ThematicChapterRef`、`ThematicMilestone`、`TopicGuide`），嚴格規範每條專題論點必須 100% 錨定於真實集數與章節 Takeaway。
2. **主題聚類與時間演進引擎 (Thematic Aggregator & Evolution Engine)**：依據語意關鍵字、概念特徵與集數時間戳（2020–2026），自動聚合相關章節並依時間軸（時間脈絡、轉折點、最新定調）結構化排序。
3. **標準化主題指南渲染器 (Topic Guide Renderer)**：產出具備目錄導航、時序演變、關鍵問答與可點擊單集 Markdown 連結的專題手冊（如 `gooaye-youtube-notes/topics/`）。
4. **漸進式技能主題路由整合 (Skill Topic Integration)**：擴充 `gooaye` 漸進式技能，使 Agent 在識別到巨觀產業或心法問題時，優先路由至主題指南，達成零額外 Token 浪費的高效檢索。
5. **統一 CLI 主題指令集**：整合至現有命令列工具，支援單一指令批次合成、特定主題預覽與引用接地完整性審計（`audit`）。

## User Stories

1. 作為一位關注 AI 硬體架構的研究員，我想要閱讀「AI 伺服器散熱與高壓供電演進」專題指南，以便於一覽 2022 至 2026 年主委對氣冷、水冷、CDU、浸沒式與 800V 電源架構的歷次觀點變化。
2. 作為一位半導體投資者，我想要閱讀「ASIC 與自研晶片供應鏈」專題指南，以便於快速掌握 Google TPU、AWS Trainium、Meta MTIA 與台灣 IP/ASIC 服務商的完整討論紀錄。
3. 作為一位剛進市場的新手投資人，我想要閱讀「主委投資心態與風險控制實戰手冊」，以便於系統化學習部位控管、停損停利紀律、勝率賠率期望值計算與生活化心態建設。
4. 作為一位 AI Coding Agent，我想要在面對泛主題提問時直接讀取主題專題指南，以便於在 1,500 tokens 內獲取數十集精華並給出具備精確集數引註的高品質回覆。
5. 作為一位資料分析師，我想要主題指南中的每一條論點都具備明確的發布日期與單集連結，以便於點擊直達該集的導航筆記或深度筆記查驗原始上下文。
6. 作為一位品質審計人員，我想要系統自動驗證主題指南中的所有引用連結均有效且與底層章節真實對齊，以便於徹底杜絕引述幻覺與死連結。
7. 作為一位開發者，我想要透過單一 CLI 指令（如 `python3 .work/cli.py topics --generate`）自動合成所有預定義主題指南，以便於快速融入持續整合與部署流程。
8. 作為一位內容策展人，我想要自訂主題關鍵字規則與分類設定檔，以便於彈性擴充新的專題（如「車用電子與碳化矽」、「記憶體循環週期」、「房地產與資產配置」）。
9. 作為一位使用手機閱讀 Markdown 筆記的使用者，我想要主題指南具有清晰的目錄（TOC）與摘要引言，以便於在不同裝置上都能獲得絕佳的閱讀體驗。
10. 作為一位依賴命令列的工程師，我想要透過 `python3 .work/cli.py topics --list` 快速檢視所有已收錄專題及其覆蓋的集數數量與時間區間。
11. 作為一位對歷史回顧感興趣的聽眾，我想要在主題指南中看到「觀點轉折里程碑 (Milestones & Inflection Points)」，以便於了解主委在市場多空反轉時如何動態修正假設。
12. 作為一位重視離線使用的開發者，我想要主題指南生成完全於本機純 Python 環境執行，無需依賴任何付費雲端 API。
13. 作為一位 Agent 技能使用者，我想要 `_index.md` 索引檔中包含主題指南的快速入口導航，以便於在第一階段檢索時即刻發現現成專題。
14. 作為一位追求簡潔的讀者，我想要主題指南提供「核心觀點速覽矩陣 (Summary Matrix)」，以便於在 30 秒內掌握各家廠商與技術路線的優劣勢比較。
15. 作為一位維護知識庫的工程師，我想要主題指南遵循既有的 Single-Context 領域文件規格與 ADR 規範，以便於知識庫維持高度一致的架構質量。

## Implementation Decisions

### 1. 領域模型擴充 (Domain Model Extensions)

在核心領域中引入以下專題實體（純不可變資料類別，遵循既有 `domain.py` 風格）：

- **`TopicDefinition`**：主題定義元數據（主題標識符、中文標題、英文 Slug、分類標籤、描述、相關關鍵字與核心概念詞彙）。
- **`ThematicChapterRef`**：關聯章節引用物件（集數編號、發布日期、章節序號、章節標題、核心觀點 Takeaway、關聯度權重）。
- **`ThematicMilestone`**：歷史轉折里程碑（時間戳、核心事件、觀點轉折摘要、代表性集數與引言）。
- **`TopicGuide`**：完整主題指南領域物件（主題元數據、時間跨度、涵蓋集數總覽、核心觀點矩陣、時序演進章節、重點問答、關聯章節引用清單）。

```python
@dataclass(frozen=True)
class ThematicChapterRef:
    episode_number: int
    published_at: str
    chapter_index: int
    heading: str
    takeaway: str
    relevance_score: float

@dataclass(frozen=True)
class TopicGuide:
    slug: str
    title: str
    description: str
    category: str
    time_span: tuple[str, str]
    key_takeaways: tuple[str, ...]
    milestones: tuple[ThematicMilestone, ...]
    chapters: tuple[ThematicChapterRef, ...]
```

### 2. 主題聚類與演進合成模組 (Topic Synthesizer)

- **單向資料流架構**：從現有的 `EpisodeNote` 與 `Chapter` 資料中抽取特徵，比對主題關鍵字庫進行加權評分（標題精準匹配、Takeaway 匹配、摘錄詞頻統計）。
- **時序排序與觀點演進聚合**：按發布日期嚴格遞增排序，自動分群為「早期佈局/摸索期」、「技術爆發/驗證期」與「成熟/分化期」等時間區間。
- **引用接地保證 (Grounding Guarantee)**：專題指南中的所有標題與 Takeaway 直接引用已通過 100% 審計的底層章節資料，杜絕二次生成幻覺。

### 3. 主題指南 Markdown 渲染規範 (Topic Guide Renderer)

- 渲染目標目錄：`gooaye-youtube-notes/topics/{slug}.md`。
- Frontmatter 規格包含 `title`, `slug`, `category`, `episodes_count`, `chapters_count`, `time_span`, `content_method: "thematic_synthesis"`。
- 內文包含：主題導言、核心結論速覽清單、時序演進大綱、按年份/階段分組的深度觀點精華、精選問答 Q&A，以及底層章節連結清單。

### 4. 漸進式技能與索引整合 (Progressive Skill Integration)

- 更新 `gooaye-youtube-notes/_index.md`，新增 `## 📚 主題專題深度指南 (Thematic Topic Guides)` 導航專區。
- 更新 `.agents/skills/gooaye/SKILL.md`，在階梯式檢索 SOP 第一階段加入主題指南優先命中判定（Stage 1.5）。

### 5. 命令列工具擴充 (CLI Integration)

- 於現有 CLI 加入 `topics` 子命令：
  - `python3 .work/cli.py topics --generate`：全量生成主題專題指南。
  - `python3 .work/cli.py topics --audit`：檢查所有專題指南的引用接地與連結有效性。
  - `python3 .work/cli.py topics --list`：列出所有已定義專題與統計概況。

## Testing Decisions

### 良好測試準則 (Good Test Principles)

- 測試僅針對**最高層可觀察行為與公開介面**，不拘泥於內部關鍵字權重計算等細節。
- 驗證合成輸出的 `TopicGuide` 物件包含正確的時間跨度、章節引用清單與格式合規性。
- 驗證生成的 Markdown 文件具備合法 Frontmatter、可解析之標題結構與有效點擊連結（無死連結、無格式錯誤）。
- 驗證 CLI 子命令 `topics --generate` 與 `topics --audit` 的執行狀態碼與終端輸出回饋。

### 核心受測接縫 (Testing Seams)

- **最高層接縫 (Single Primary Seam)**：`TopicGuideSynthesizer` 介面（`synthesize_topic(topic_def, all_episodes) -> TopicGuide` 與 `synthesize_all_topics() -> list[TopicGuide]`），以及對應的 `render_topic_guide(guide) -> str` 渲染器。
- **CLI 整合接縫**：透過 `subprocess` 執行 `python3 .work/cli.py topics` 驗證端到端命令列行為。

### 既有測試參考 (Prior Art)

- 參考 `.work/test_domain.py` 與 `.work/test_markdown_renderer.py` 的資料模型與 Markdown 渲染測試結構。
- 參考 `.work/test_episode_synthesizer.py` 的批次合成與審計測試模式。
- 參考 `.work/test_installer.py` 的 CLI 命令列執行測試規範。

## Out of Scope

- 外部即時資料抓取或自動產生未定義主題的無監督分群。
- 即時對話式 LLM 線上主題問答伺服器（仍由 Agent 透過技能按需載入 Markdown 指南）。
- 針對非 Gooaye 來源的第三方外部文章或研報整合。

## Further Notes

- 首批預計內建的核心專題涵蓋：
  1. `ai-hardware-and-semiconductor` (AI 伺服器、散熱、電力與 ASIC 自研晶片)
  2. `investment-mindset-and-risk-control` (主委核心心態、部位管理、停損與期望值)
  3. `macro-cycle-and-asset-allocation` (總體經濟循環、聯準會降息循環、房產與美股配置)
  4. `apple-and-consumer-electronics` (Apple 供應鏈、智慧型手機與消費性電子週期)
- 所有專題指南與底層 689 集 / 5,299 章節保持 100% 同步與一致性。
