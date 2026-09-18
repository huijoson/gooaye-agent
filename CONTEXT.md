# Domain Context & Glossary (CONTEXT.md)

本文件定義 Gooaye 筆記處理系統的核心領域概念、模組架構、職責邊界與命名規範。

---

## 核心領域實體 (Core Domain Entities)

### 1. Episode (`EpisodeMetadata`)
- 正式 Knowledge Base Publication 涵蓋 EP1 至 EP693（全套共 693 集完整無缺漏；EP232 已自逐字稿封存庫補齊）。先前 legacy release 只涵蓋 689 支影片；目前的第 693 集 EP693 是已驗證並發布的 Episode Source。
- 每集包含集數編號、YouTube 原始標題、第三方策展標題、發布日期、發布日期來源、影片片長與完整逐字稿。

### 2. Full Transcript (完整逐字稿)
- 取自公開非官方逐字稿網站的完整文字記錄，為所有章節觀念與條列摘錄的唯一真實依據。

### 3. Curated Summary (第三方摘要)
- 來自外部索引的集數簡介。系統規則嚴格規定：第三方摘要**僅作為主題檢索提示與輔助參考**，禁止直接複製成筆記段落或洩漏至章節標題中，亦不得限制或決定章節切分數量。

### 4. Chapter Evidence (`ChapterEvidence`)
- 每章從完整逐字稿中依討論順序錨定的真實引述句（短摘錄），保留原始脈絡並作為章節標題命名與核心觀點推導的唯一內容依據。
- 在導航層 (`EPxxxx.md`) 收錄 2 條核心引述；在深度層 (`EPxxxx.full.md`) 收錄 4–8 條完整擴充引述句。
- 欄位包含：`index: int`, `seed_title: str`, `excerpts: tuple[str, ...]`, `position: int`。

### 5. Chapter Heading (章節標題)
- 依據該章摘錄提煉之 8–32 字繁體中文標題。必須同時涵蓋摘錄之核心概念，不得為口語殘句、機械黏合字串、泛稱詞或摘要抄襲。

### 6. Chapter Takeaway (核心觀點)
- 針對該章逐字稿摘錄提煉之單句核心觀點總結（20–60 字繁體中文陳述判斷句）。
- 必須具備明確的主詞、論點與邏輯結論，實體名詞嚴格接地（Grounding）於逐字稿，嚴禁「主委在本段分享了/探討了」等元敘述空話。

### 7. Chapter (`Chapter`)
- 結構化領域物件：包含章節序號 (`index`)、最終解析標題 (`heading`)、核心觀點 (`takeaway`)、逐字稿真實摘錄清單 (`excerpts`) 以及在逐字稿中的字元位置 (`position`)。

### 8. EpisodeNote (`EpisodeNote`)
- 封裝單集完整元數據、觀念章節清單與資料來源說明，具備 `render_markdown(mode="slim" | "full")` 分別生成導航層 Markdown (`EPxxxx.md`) 與深度層 Markdown (`EPxxxx.full.md`) 的能力。
- Frontmatter 標註 `content_method: "hybrid_extractive_distilled"`。

### 9. SynthesisSummary (`SynthesisSummary`)
- 批次生成之摘要統計物件：包含全集總數、章節總數、總時長、章節分布統計與單集筆記領域物件序列。

### 10. Episode Acquisition（單集來源取得）
- 將指定 Episode 的公開上游資料納入本地語料庫的明確邊界；成功只代表該集已形成可供合成使用的 Episode Source Snapshot，不包含筆記合成或正式發布。

### 11. Episode Source Snapshot（單集來源快照）
- 同一 Episode 的完整來源集合：官方節目 metadata、第三方策展 metadata 與 Full Transcript；三者集數必須一致並通過完整性驗證。
- 不包含原始音訊、生成後的 Episode Note 或 Knowledge Base Publication。

### 12. Knowledge Base Publication（知識庫發布）
- 一份可獨立使用的完整知識庫發行版；目前涵蓋 693 集雙層 Episode Notes、四份 Topic Guides、索引與導覽文件，並以 SHA-256 Manifest 識別其完整內容。
- 與 689-video legacy release 有明確區別；只有完整 corpus 才是 Publication。

### 13. Preview（預覽）
- 指定 Episode 或 Topic 的局部、顯式、隔離產出，用於檢查結果但不構成正式知識庫發布。
- 不得位於 Knowledge Base Publication 根目錄或其任何子目錄，亦不得取代 Publication。

### 14. Cold Transcript Archive（永久逐字稿封存庫）
- 位於專案根目錄 `transcripts/` 的獨立且完整的全集原始逐字稿集合（`EPxxxx.md` 與 `README.md` 索引）。
- 專門作為防範外部非官方逐字稿網站下線或資料失聯的獨立永久冷封存層，具備完整 YAML Frontmatter 與一字一句的原始逐字內容。
- 獨立於 `.work/` 內部處理管線與 `gooaye-youtube-notes/` 結構化發布知識庫之外。

---

## 核心深模組與分層架構 (Deep Modules & Layered Architecture)

系統遵循高內聚、低耦合、深介面（Deep Interface）與單向資料流原則，拆分為以下模組：

### 9. Episode Source Repository (`episode_source_repository.py`)
- 隱藏 legacy corpus 與 `.work/episode-sources/EPxxxx/` normalized snapshots 的儲存差異，normalized snapshot 存在時優先讀取。
- 負責 snapshot 驗證、content hash、staging directory、取代衝突、`--force` 與 rollback；不負責 HTTP 或筆記合成。
- **介面 (Interface)**：`commit(snapshot, force=False)`、`verify(number)`、`get_metadata(number)`、`load_transcript(number)` 與 `episode_numbers`。

### 10. Episode Acquirer (`episode_acquirer.py`)
- 將 YouTube RSS 的 identity/title、SoundOn RSS 的 duration/date，以及非官方 archive 的策展 metadata/Full Transcript 對齊成一個 `EpisodeSourceSnapshot`。
- **介面 (Interface)**：`acquire(number, force=False)` 與 `acquire_latest(force=False)`。三個必要來源未齊全時失敗，不改抓音訊轉錄、不自動合成或發布。

### 11. Transcript Processor (`transcript_processor.py`)
- **`TranscriptSanitizer`**：負責多階段廣告過濾（開頭贊助區塊、贊助宣告、特定贊助品牌如銀座白石/Sony 耳機等之業配詞、過渡橋段）、結尾重點回顧過濾、Markdown 標題/引言清除與摘錄句標準化。
- **`TranscriptSegmenter`**：負責逐字稿標點斷句（`segment_sentences`）、目標字數語意分塊（`make_chunks`）與第三方摘要主題種子切分（`split_seeds`）。
- **`TranscriptFeatureExtractor`**：負責中英文字詞特徵提取（`features`）與加權重疊相似度計算（`similarity`）。

### 12. Evidence Extractor (`evidence_extractor.py`)
- **`EvidenceExtractor`**：純內存章節摘錄抽取引擎。依據主題種子與逐字稿塊之特徵相似度排序定位候選錨點，在周邊視窗中篩選符合長度且非廣告之真實句子，並執行摘要防碰撞與章節去重，最終按逐字稿出現順序生成 `list[ChapterEvidence]`。

### 13. Heading Quality Engine (`heading_quality_engine.py`)
- 評估、診斷與修復章節標題品質的深模組。
- **介面 (Interface)**：
  - `evaluate(heading, excerpts, summary) -> bool`：快速布林閘門。
  - `diagnose(heading, excerpts, summary) -> QualityReport`：完整瑕疵分類與 LLM 重試反饋提示。
  - `extract_phrase_candidates(text, guide) -> list[str]`：從摘錄中提取具代表性、長度合宜且無口語/斷詞瑕疵之名詞短語候選。
  - `repair(heading, excerpts, summary, used_headings) -> str`：多層級確定性修復演算法（弱接地修補、短語配對、乾淨 token 掃描與安全保底）。

### 14. Heading Resolver (`heading_resolver.py`)
- 標題解析策略接縫 (Seam)：
  - **`CachedHeadingResolver`**：磁碟 JSON 快取適配器，載入後由 `HeadingQualityEngine` 逐一驗證品質。
  - **`DeterministicHeadingResolver`**：基於品質引擎的純 Python 確定性保底解析器。
  - **`CompositeHeadingResolver`**：快取/主解析器優先，驗證未通過自動降級至確定性保底的多層複合解析器。
  - **`OllamaHeadingResolver`**：基於本地 LLM（如 Qwen 4B）的結構化標題生成器，整合品質引擎診斷反饋重試機制。

### 15. Takeaway Quality Engine (`takeaway_quality_engine.py`)
- 評估與驗證單章「核心觀點 (Takeaway)」品質的深模組。
- 檢驗維度包括：完整陳述判斷句結構、繁體中文語法、實體名詞逐字稿接地性 (Entity Grounding)、反幻覺與反泛稱元敘述（禁止「主委分享了/探討了」等）。

### 16. Markdown Renderer (`markdown_renderer.py`)
- 負責標準化 Markdown 渲染輸出：
  - `render_episode(note, mode="slim" | "full") -> str`：渲染單集導航層 (`EPxxxx.md`) 或深度層 (`EPxxxx.full.md`) Markdown 文件。
  - `render_index(notes, summary) -> str`：渲染 `_index.md` 索引文件。
  - `render_readme(notes, summary) -> str`：渲染 `README.md` 總覽文件。

### 17. Episode Note Synthesizer (`episode_synthesizer.py`)
- 核心調度深模組：將 `EvidenceExtractor`、`HeadingResolver`、`TakeawayResolver` 與 `MarkdownRenderer` 組合成完整單向資料流。
- 單集來源只透過 `EpisodeSourceRepository` 讀取，不知道 legacy/normalized 檔案佈局。
- **介面 (Interface)**：
  - `get_metadata(number) -> EpisodeMetadata`：獲取並對齊單集元數據。
  - `extract_evidence(number) -> list[ChapterEvidence]`：抽取單集章節摘錄。
  - `synthesize_episode(number, resolver) -> EpisodeNote`：完整合成單集筆記。
  - `synthesize_all(output_dir, resolver, max_workers) -> SynthesisSummary`：支援多執行緒並行合成全集筆記 (`EPxxxx.md` + `EPxxxx.full.md`)、`_index.md` 與 `README.md`。
  - `audit(resolver) -> dict`：對全集執行 100% 標題與核心觀點瑕疵診斷審計。

### 18. Unified CLI (`cli.py`)
- 整合式命令列工具：
  - `download`：以 `--episode N` 或 `--latest` 取得單集完整來源 snapshot；已存在的變動內容需顯式 `--force`。
  - `synthesize`：批次或單集生成 Markdown 筆記（支援 `--workers`, `--resolver`, `--dry-run`, `--out-dir`）。
  - `audit`：全集標題與觀點品質審計與瑕疵統計。
  - `topics`：主題專題指南批次合成（`--generate`）、接地審計（`--audit`）與清單檢視（`--list`）。
  - `diagnose`：單一標題、觀點與摘錄品質診斷與修復測試。
  - `doctor`：環境、數據來源與快取完整性體檢。
  - `publish`：唯一正式發布入口；建立、驗證並交易式安裝完整 Manifest-managed Knowledge Base Publication。
  - `verify`：唯讀驗證 legacy 或 Manifest-managed Knowledge Base Publication 的結構、完整性與 digest。

### 21. Knowledge Base Publisher (`knowledge_base_publisher.py`)
- 正式 Publication 的唯一生命週期深模組；從同一批記憶體中的 Episode Notes 與 Topic Guides 建立完整 sibling staging tree、寫入 Manifest、驗證後才交易式替換目的地。
- **介面 (Interface)**：`publish(request) -> PublicationManifest` 與 `verify(root) -> PublicationVerification`；失敗時保留舊的完整 Publication，未知的非空目的地一律拒絕。

### 19. Topic Guide Synthesizer & Auditor (`topic_synthesizer.py`)
- 跨集數主題專題合成與品質審計深模組：
  - **`TopicDefinition`**：定義主題標識、關鍵字、核心概念與分類。
  - **`ThematicChapterRef`**：包含集數編號、日期、章節標題、Takeaway 與權重關聯評分的引用物件。
  - **`TopicGuideSynthesizer`**：從目前 693 集 Manifest-managed Publication 的筆記中依時序聚合相關章節、提煉年度里程碑與核心結論矩陣。
  - **`TopicGuideRenderer`**：渲染標準主題專題 Markdown 手冊（`gooaye-youtube-notes/topics/{slug}.md`）與主題總覽索引（`topics/README.md`）。
  - **`TopicQualityAuditor`**：100% 驗證專題手冊之章節引用存在性、發布日期對齊度與點擊連結有效性。

---

## 標題瑕疵分類體系 (Defect Categories)

- **`FORMAT`**：長度超出 8–36 字、標點未成對（括號/書名號/引號）、殘留省略號或結尾殘句。
- **`GENERIC_TERMS`**：包含「主題、其他、雜談、市場話題、聽眾問答、實務建議、本段重點、Q&A」等。
- **`TRANSITION_PREFIX`**：以「另外、接著、轉向、的、了、是、個、這個、比較、甚至是在、希望大家」等開頭。
- **`CONVERSATIONAL_FRAGMENT`**：保留說話第一/第二人稱（我、你、我們、你們）、口語程度詞（滿、超）或填充詞（東西、事情、狀況、樣子、而已）之長切片。
- **`MACHINE_GLUE`**：以連詞（與/及/對照）生硬拼接兩摘錄之長子字串，缺乏概念收斂。
- **`SUMMARY_LEAKAGE`**：標題抄襲第三方摘要或使用僅存在於摘要而未在摘錄中出現之詞彙。
- `WEAK_GROUNDING`：標題缺乏與摘錄之核心詞彙重疊（Bigram 覆蓋度不足）。
- `BROKEN_LATIN`：英文單字或型號遭截斷（如 `Apple Watc`、`Analysi`、`Joe Rog`）。
- `UNBALANCED_SYNTAX`：括號、引號、書名號未成對閉合。

---

## 代理與技能層 (Agent & Skill Layer)

### 20. Gooaye Skill (`.agents/skills/gooaye/SKILL.md`)
- **定位**：極低 Token 待機開銷（~30 tokens）的漸進式按需技能。
- **雙模態機制 (Dual-Mode)**：
  - **Archive Query (客觀檢索模式)**：檢索目前 693 集 Manifest-managed Publication 的結構化筆記與跨集數主題專題手冊，提供精確集數、章節、核心觀點與逐字稿引述。
  - **Mindset Roasting (主委心態健檢模式)**：切換謝孟恭口吻，基於部位管理、停損紀律、期望值計算進行風險拷問。
- **階梯式檢索 (Multi-Stage Progressive Search)**：
  - Stage 1: 先在 `_index.md` 與 `episodes/` 中透過語意或關鍵字定位 1–3 集（~150KB 全域索引）。
  - Stage 1.5: 宏觀產業與心態問題優先讀取 `topics/{slug}.md` 主題手冊（~1.5k tokens）。
  - Stage 2: 讀取命中的 `episodes/EPxxxx.md` 導航筆記（含核心觀點與精選引述，~1k tokens）。
  - Stage 2.5 (可選): 若需深入討論脈絡與完整引述，讀取 `episodes/EPxxxx.full.md` 深度筆記。
  - Stage 3 (可選): 僅在需確認底層逐字稿細節時才定點檢索；優先讀取 `.work/episode-sources/EPxxxx/transcript.md`，無 normalized snapshot 時才讀取 `.work/full-transcripts/EPxxxx.md`。
