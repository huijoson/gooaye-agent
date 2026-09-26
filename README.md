# Gooaye Agent & Knowledge Base (股癌知識庫與智能代理)

[![Episodes](https://img.shields.io/badge/Episodes-700%20Videos-blue.svg)](gooaye-youtube-notes/_index.md)
[![Chapters](https://img.shields.io/badge/Chapters-5%2C384%20Topics-orange.svg)](gooaye-youtube-notes/_index.md)
[![Topic Guides](https://img.shields.io/badge/Topics-4%20Playbooks-green.svg)](gooaye-youtube-notes/topics/README.md)
[![Cold Transcripts](https://img.shields.io/badge/Transcripts-700%20Transcripts-red.svg)](transcripts/README.md)
[![Skill Architecture](https://img.shields.io/badge/Antigravity-Progressive%20Skill-purple.svg)](.agents/skills/gooaye/SKILL.md)

本專案將《Gooaye 股癌》目前可用的 **700 集 Episode Source**（EP1–EP700 全套完整無缺漏；550+ 小時）經由雙層混合架構（Dual-Tier Hybrid Extractive-Distilled Pipeline），整理為結構化觀念章節、單句核心觀點判斷與真實逐字稿引述，並提煉出 **4 大跨集數主題專題手冊**；全套知識庫封裝為符合 Antigravity 規範之極低 Token 待機開銷（~30 tokens）的漸進式按需技能（Progressive Skill）。此外，專案亦設立獨立之 **永久完整逐字稿冷封存庫（Cold Transcript Archive）**，防止外部站點失聯。

> 先前的 legacy release 僅有 **689 支影片**；目前正式 Knowledge Base Publication 為 700 集（EP232 已自逐字稿庫補齊）。`download` 只建立或驗證 Episode Source Snapshot，絕不自動合成或發布。

> [!NOTE]
> **最新集數與收錄狀態說明 (Episode Status & Sync Tracking)**：
> - **本專案知識庫與冷封存庫**：完整收錄 **EP1–EP700**（全套 700 集無缺漏，涵蓋至 2026-09-26 之 EP700）。
> - **官方節目最新發布進度**：截至 2026-09-26 查核，官方 SoundOn / YouTube 已更新至 **EP700**（2026-09-26 最新集：`EP700 | 🪭`）。
> - **來源與校對狀態**：EP1–EP693 來自第三方逐字稿；EP694–EP700 依使用者要求改以官方 SoundOn RSS 音訊、本機 MLX Whisper large-v3-turbo 轉錄（[ADR 0006](docs/adr/0006-official-audio-asr-fallback.md)）。機器轉錄尚未人工校對，專有名詞與數字可能誤聽；引用精確措辭時應核對原音。

---

## 📁 專案結構導覽 (Project Structure)

```text
gooaye-agent/
├── .agents/                                # AI Agent 技能與擴充定義
│   └── skills/
│       └── gooaye/
│           └── SKILL.md                    # Gooaye 漸進式雙模態技能主定義檔
│
├── transcripts/                            # 700 集完整逐字稿永久封存庫 (Cold Archive)
│   ├── README.md                           # 全集逐字稿索引表與元數據導覽
│   └── EP0001.md ~ EP0700.md               # 逐字稿全文與來源、校對狀態 (含 YAML Frontmatter)
│
├── gooaye-youtube-notes/                    # 700 集受 Manifest 管理的正式知識庫
│   ├── README.md                           # 筆記資料集統計與限制說明
│   ├── _index.md                           # 全集章節大綱與關鍵字快速檢索表 (Stage 1 索引)
│   ├── publication-manifest.json           # 所有發布檔案的 SHA-256 Manifest
│   ├── topics/                             # 跨集數深度主題專題手冊 (Stage 1.5 專題)
│   │   ├── README.md                       # 主題專題總覽與使用指引
│   │   ├── ai-hardware-and-semiconductor.md
│   │   ├── investment-mindset-and-risk-control.md
│   │   ├── macro-cycle-and-asset-allocation.md
│   │   └── apple-and-consumer-electronics.md
│   └── episodes/                           # EP0001.md ~ EP0700.md 雙層觀念筆記（全套完整無缺漏）
│
├── docs/                                   # 系統架構規格與決策紀錄
│   ├── adr/
│   │   ├── 0001-progressive-gooaye-skill.md # ADR：漸進式按需技能架構決策
│   │   ├── 0002-hybrid-extractive-distilled-notes.md # ADR：雙層混合筆記架構決策
│   │   ├── 0003-incremental-episode-source-acquisition.md # ADR：增量單集來源取得
│   │   ├── 0004-transactional-knowledge-base-publication.md # ADR：交易式知識庫發布
│   │   ├── 0005-cold-transcript-archive.md # ADR：永久完整逐字稿冷封存庫決策
│   │   └── 0006-official-audio-asr-fallback.md # ADR：官方音訊 ASR 補集政策
│   └── specs/                              # 系統規格書
│
├── scripts/                                # 安裝與自動化管理腳本
│   ├── install-skill.sh                    # 一鍵安裝 / Symlink 技能腳本 (全域或指定專案)
│   └── export_cold_transcripts.py          # 匯出 / 同步全集永久逐字稿庫腳本
│
├── .work/                                  # 數據處理、合成管道與品質稽核核心引擎
│   ├── cli.py                              # 統一命令列介面 (download / synthesize / audit / publish 等)
│   ├── cold_transcript_exporter.py         # 冷封存逐字稿格式化與自動同步模組
│   ├── domain.py                           # 核心領域物件 (EpisodeNote, Chapter, TopicGuide 等)
│   ├── episode_synthesizer.py              # 單集與全集批次並行合成調度器
│   ├── episode_acquirer.py                 # 公開上游來源對齊與單集取得邊界
│   ├── episode_source_repository.py        # legacy/normalized 來源、驗證與交易式取代
│   ├── episode-sources/                    # per-episode normalized source snapshots
│   ├── topic_synthesizer.py                # 跨集數主題專題合成與審計引擎
│   ├── heading_quality_engine.py           # 標題 9 大瑕疵品質診斷引擎
│   ├── takeaway_quality_engine.py          # 核心觀點 Takeaway 品質診斷引擎
│   └── full-transcripts/                   # 540+ 小時原始完整逐字稿庫 (Stage 3 深度查證)
│
├── CONTEXT.md                              # 系統領域概念定義、分層架構與介面規範
└── README.md                               # 本專案總覽與使用手冊
```

---

## 🚀 技能安裝與使用方式 (Skill Installation)

本專案支援多種安裝與整合方式，讓您在本地專案或跨所有工作區隨時調用 Gooaye 技能：

### 方式一：在本專案直接使用（免安裝）
如果您在當前 `gooaye-agent` 專案目錄下開啟 Antigravity，Agent 會自動偵測到 [`.agents/skills/gooaye/SKILL.md`](.agents/skills/gooaye/SKILL.md)，**無需任何安裝即可直接提問**。

---

### 方式二：全域安裝（推薦，所有專案皆可調用）
透過內建的安裝腳本，將技能軟連結（Symlink）至 Antigravity 的全域設定目錄：

```bash
# 執行一鍵全域安裝（建立 Symlink，本專案筆記更新時自動同步）
./scripts/install-skill.sh --global

# 或若要以實體檔案複製安裝：
./scripts/install-skill.sh --global --copy
```

**手動安裝方式**：
```bash
mkdir -p ~/.gemini/config/skills
ln -s "$(pwd)/.agents/skills/gooaye" ~/.gemini/config/skills/gooaye
```

安裝完成後，無論您在電腦的哪一個資料夾開啟 Antigravity，Agent 都能隨時啟用 Gooaye 知識庫。

---

### 方式三：安裝至其他工作區專案
若您想在另一個獨立專案中使用 Gooaye 技能：

```bash
./scripts/install-skill.sh --target /path/to/your-other-project
```
這將會在目標專案的 `.agents/skills/` 下建立指向本技能的符號連結。

---

### 方式四：其他 AI Agent 與工具整合
- **Claude Code**：建立符號連結至 `.claude/skills/gooaye` 或在 `CLAUDE.md` 引用 `.agents/skills/gooaye/SKILL.md`。
- **Cursor / Windsurf / Roo Code / Cline**：可在系統提示或專案規則（`.cursorrules` / `.windsurfrules`）中引入本技能的階梯式檢索 SOP 與雙模態協定。

---

## 🎯 雙模態互動指南 (Dual-Mode Interaction)

本技能具備智慧意圖分流，支援以下兩種核心模式：

### 模式 A：歷史觀點與集數查證 (Archive Query Mode)
> **適用情境**：查詢主委對特定標的、產業、技術或歷史事件的看法與時間點。

*   **提問範例**：
    *   *「主委過去在哪些集數聊過 Google 的 COT 或 ASIC 趨勢？」*
    *   *「EP690 主要講了什麼？請列出重點與逐字稿引述。」*
    *   *「幫我查主委對海運股或航運週期的看法轉折。」*
*   **回覆特色**：
    *   客觀中立、嚴格基於逐字稿事實。
    *   提供確切集數、發布日期、章節標題與可點擊之 Markdown 筆記連結。

---

### 模式 B：主委投資心態靈魂拷問 (Mindset Roasting Mode)
> **適用情境**：面臨套牢、追高 FOMO、停損猶豫、槓桿失控或投資焦慮。

*   **提問範例**：
    *   *「我買在最高點現在套牢 30%，捨不得停損怎麼辦？」*
    *   *「看群組都在狂推某飆股，我是不是該開槓桿跟上？」*
    *   *「獲利抱過一座山又回吐，心態好崩潰，請主委罵醒我。」*
*   **回覆特色**：
    *   切換謝孟恭標誌性口吻（大白話、幽默嘴砲、生活化比喻）。
    *   逐一拷問：**部位大小**（睡得著嗎？）、**進場理由與停損紀律**（破線為何當傳家寶？）、**勝率與期望值**（算不算得過？）。
    *   嚴守紀律：❌ 絕不報明牌 ❌ 絕不護航投機僥倖心理。

---

## ⚙️ 開發者與數據管道工具 (Developer & CLI)

本專案包含完整的資料處理、抽取、標題診斷與筆記合成引擎，位於 `.work/` 目錄：

```bash
# 1. 取得指定集數或最新集的完整來源 snapshot
python3 .work/cli.py download --episode 693
python3 .work/cli.py download --latest

# 已存在且內容相同會 no-op；上游內容有變動時需顯式覆蓋
python3 .work/cli.py download --episode 693 --force

# 2. 執行環境與數據源體檢
python3 .work/cli.py doctor

# 3. 執行全集 700 集標題與觀點品質審計
python3 .work/cli.py audit

# 4. 執行四大主題專題手冊品質審計
python3 .work/cli.py topics --audit

# 5. 正式發布：完整合成、Manifest 驗證與交易式安裝
python3 .work/cli.py publish --output-dir gooaye-youtube-notes --resolver composite --workers 8

# 6. 驗證正式發布（Manifest digest、圖結構與完整性）
python3 .work/cli.py verify --output-dir gooaye-youtube-notes

# 7. 僅產生隔離 Preview；不得指定正式發布根目錄或其子目錄
python3 .work/cli.py synthesize --episode 693 --output-dir /tmp/gooaye-preview-693 --resolver composite

# 8. 匯出或更新獨立完整逐字稿永久封存庫 (transcripts/)
python3 scripts/export_cold_transcripts.py --all
python3 scripts/export_cold_transcripts.py --episode 693

# 9. 執行核心模組單元測試套件
pytest .work/
```

官方音訊 ASR 補集（需先備妥已核對集數的音訊與官方 RSS metadata，並在 `.venv` 安裝可選的 `mlx-whisper`、`opencc-python-reimplemented==0.1.7`，另備妥 `ffmpeg` 及本機模型）：

```bash
.venv/bin/python scripts/transcribe_episode_audio.py .work/audio/EP069{4,5,6,7,8,9}.mp3 --output-dir .work/asr-transcripts
.venv/bin/python scripts/import_asr_episodes.py --metadata .work/asr-transcripts/official-metadata.json --episodes 694 695 696 697 698 699 --audio-dir .work/audio --asr-dir .work/asr-transcripts
```

ASR 補集另保留 `.work/asr-transcripts/EPxxxx.json` 的音訊 SHA-256、模型版本、轉錄時間及分段時間證據；來源快照記錄官方音訊來源。匯入逐字稿以 OpenCC `s2twp` 正規化繁體字，JSON 保留原始轉錄；人工檢視的 `content_start_segment`（從 0 起算）僅讓筆記合成略過開頭業配，封存仍保留全稿。合成階段會合併相鄰 ASR 分段並補標點以利摘錄；這些標點不代表原始句界。ASR 來源匯入會同步冷封存；更新正式筆記仍須執行 `publish`。

`--latest` 以 YouTube RSS 的最新官方集數為目標；若 archive 索引或逐字稿尚未齊全，命令會回報 `archive pending` 而不降級。缺少 SoundOn 集目則是來源不一致（source mismatch），會明確失敗。第一版只能取得仍在官方 RSS window 內的新集，或已有 legacy metadata 的舊集；其他集數會明確失敗。每次成功執行 `download` 都會自動將新集數的完整逐字稿同步匯出至 `transcripts/` 封存庫。

`publish` 是正式 Publication 的唯一寫入入口：它在同層 staging 目錄完整建立 700 集筆記與四份 Topic Guide、寫入 SHA-256 Manifest、驗證整個圖後，才在目的地鎖定期間交易式取代舊根目錄。請預留至少 **兩倍既有發布目錄大小加 100 MiB** 的可用空間；發布失敗會保留先前完整版本並清理暫存 sibling。`verify` 只讀取並驗證現有 legacy 或 Manifest-managed 根目錄。Preview 是局部、顯式且隔離的產出，永遠不能取代正式 Publication。

### 相關架構文件
- [CONTEXT.md](CONTEXT.md)：核心領域概念、深模組介面與品質閘門標準。
- [ADR 0001](docs/adr/0001-progressive-gooaye-skill.md)：漸進式按需技能架構決策紀錄。
- [ADR 0002](docs/adr/0002-hybrid-extractive-distilled-notes.md)：雙層混合筆記架構決策紀錄。
- [ADR 0003](docs/adr/0003-incremental-episode-source-acquisition.md)：增量單集來源取得、驗證與取代政策。
- [ADR 0004](docs/adr/0004-transactional-knowledge-base-publication.md)：完整知識庫的交易式發布與 Manifest 管理政策。
- [ADR 0005](docs/adr/0005-cold-transcript-archive.md)：永久完整逐字稿冷封存庫（Cold Archive）架構決策紀錄。
- [ADR 0006](docs/adr/0006-official-audio-asr-fallback.md)：官方音訊 ASR 補集、來源證據與校對狀態。
- [完整逐字稿封存庫](transcripts/README.md)：700 集逐字稿與來源索引。
- [主題專題目錄](gooaye-youtube-notes/topics/README.md)：四大主題專題手冊。
- [全集索引表](gooaye-youtube-notes/_index.md)：700 集完整章節索引。

---

## 📄 免責聲明 (Disclaimer)

- 本專案所有逐字稿與結構化筆記僅供學術研究、觀念索引與個人學習使用。
- 節目內容與 AI 產生之回覆均不構成任何形式的投資建議或買賣推薦。

---

## 📜 授權條款 (License)

本專案基於 [MIT License](LICENSE) 開源。
