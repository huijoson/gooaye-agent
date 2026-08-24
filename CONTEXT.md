# Domain Context & Glossary (CONTEXT.md)

本文件定義 Gooaye 筆記處理系統的核心領域概念、模組架構與命名規範。

---

## 核心領域實體 (Core Domain Entities)

### 1. Episode (單集)
- 涵蓋 YouTube 公開清單中 EP1 至 EP690（目前共 689 支影片，缺 EP232）。
- 每集包含集數編號、YouTube 原始標題、第三方策展標題、發布日期、影片片長與完整逐字稿。

### 2. Full Transcript (完整逐字稿)
- 取自公開非官方逐字稿網站的完整文字記錄，為所有章節觀念與條列摘錄的唯一真實依據。

### 3. Curated Summary (第三方摘要)
- 來自外部索引的集數簡介。系統規則嚴格規定：第三方摘要**僅作為主題檢索提示**，禁止直接複製成筆記段落或洩漏至章節標題中。

### 4. Chapter Evidence (章節摘錄)
- 每章從完整逐字稿中依討論順序錨定的**兩條真實引述句**（短摘錄），保留原始脈絡並作為章節標題命名的唯一內容依據。

### 5. Chapter (觀念章節)
- 結構化領域物件：包含章節序號、標題、兩條逐字稿摘錄以及在逐字稿中的字元位置。

### 6. Chapter Heading (章節標題)
- 依據該章兩段摘錄提煉之 8–32 字繁體中文標題。必須同時涵蓋兩段摘錄之核心概念，不得為口語殘句、機械黏合字串、泛稱詞或摘要抄襲。

### 7. EpisodeNote (單集筆記領域物件)
- 封裝單集完整元數據、觀念章節清單與資料來源說明，具備 `render_markdown()` 生成標準 Markdown 文件的能力。

---

## 核心深模組 (Deep Modules)

### 8. Episode Note Synthesizer (`EpisodeNoteSynthesizer`)
- 單集筆記合成深模組：將逐字稿前處理、廣告過濾、章節摘錄提取、標題解析與 Markdown 渲染整合為單向資料流。
- **介面 (Interface)**：
  - `extract_evidence(number) -> list[ChapterEvidence]`：直接從逐字稿與摘要提取內存章節摘錄，終結對磁碟 Markdown 檔案的反向正則解析。
  - `synthesize_episode(number) -> EpisodeNote`：完整合成單集筆記領域物件。
  - `synthesize_all(output_dir) -> SynthesisSummary`：批次生成全集筆記、`_index.md` 與 `README.md`。

### 9. Heading Resolver (`HeadingResolver`)
- 標題解析策略接縫 (Seam)：
  - `CachedHeadingResolver`：磁碟 JSON 快取適配器。
  - `DeterministicHeadingResolver`：基於品質引擎的純 Python 確定性保底解析器。
  - `CompositeHeadingResolver`：快取優先、確定性保底的多層複合解析器。

### 10. Heading Quality Engine (`HeadingQualityEngine`)
- 評估、診斷與修復章節標題品質的深模組。
- **介面 (Interface)**：
  - `evaluate(heading, excerpts, summary) -> bool`：快速布林閘門。
  - `diagnose(heading, excerpts, summary) -> QualityReport`：完整瑕疵分類與 LLM 重試反饋提示。
  - `repair(heading, excerpts, summary, used_headings) -> str`：確定性降級修復演算法。

### 11. Defect Categories (標題瑕疵分類)
- **`FORMAT`**：長度超出 8–36 字、標點未成對（括號/書名號/引號）、殘留省略號或結尾殘句。
- **`GENERIC_TERMS`**：包含「主題、其他、雜談、市場話題、聽眾問答、實務建議、本段重點、Q&A」等。
- **`TRANSITION_PREFIX`**：以「另外、接著、轉向、的、了、是、個、這個、比較」等開頭。
- **`CONVERSATIONAL_FRAGMENT`**：保留說話第一/第二人稱（我、你）、口語程度詞（滿、超）或填充詞（東西、事情、狀況、樣子、而已）之長切片。
- **`MACHINE_GLUE`**：以連詞（與/及/對照）生硬拼接兩摘錄之子字串，缺乏概念收斂。
- **`SUMMARY_LEAKAGE`**：標題抄襲第三方摘要或使用僅存在於摘要而未在摘錄中出現之詞彙。
- **`WEAK_GROUNDING`**：標題缺乏與摘錄一或摘錄二之核心詞彙重疊（Bigram 覆蓋度不足）。
- **`BROKEN_LATIN`**：英文單字或型號遭截斷（如 `Apple Watc`、`Analysi`）。
