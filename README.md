# Gooaye Agent & Knowledge Base (股癌知識庫與智能代理)

[![Episodes](https://img.shields.io/badge/Episodes-689%20Videos-blue.svg)](gooaye-youtube-notes/_index.md)
[![Chapters](https://img.shields.io/badge/Chapters-5%2C299%20Topics-orange.svg)](gooaye-youtube-notes/_index.md)
[![Topic Guides](https://img.shields.io/badge/Topics-4%20Playbooks-green.svg)](gooaye-youtube-notes/topics/README.md)
[![Skill Architecture](https://img.shields.io/badge/Antigravity-Progressive%20Skill-purple.svg)](.agents/skills/gooaye/SKILL.md)

本專案將《Gooaye 股癌》YouTube 公開清單中 **689 支影片（540+ 小時）** 的完整逐字稿，經由雙層混合架構（Dual-Tier Hybrid Extractive-Distilled Pipeline），整理為 **5,299 個結構化觀念章節**、**單句核心觀點判斷** 與 **真實逐字稿引述**，並提煉出 **4 大跨集數主題專題手冊**；全套知識庫封裝為符合 Antigravity 規範之極低 Token 待機開銷（~30 tokens）的漸進式按需技能（Progressive Skill）。

---

## 📁 專案結構導覽 (Project Structure)

```text
gooaye-agent/
├── .agents/                                # AI Agent 技能與擴充定義
│   └── skills/
│       └── gooaye/
│           └── SKILL.md                    # Gooaye 漸進式雙模態技能主定義檔
│
├── gooaye-youtube-notes/                    # 689 集已清洗與結構化之觀念筆記庫
│   ├── README.md                           # 筆記資料集統計與限制說明
│   ├── _index.md                           # 全集章節大綱與關鍵字快速檢索表 (Stage 1 索引)
│   ├── topics/                             # 跨集數深度主題專題手冊 (Stage 1.5 專題)
│   │   ├── README.md                       # 主題專題總覽與使用指引
│   │   ├── ai-hardware-and-semiconductor.md
│   │   ├── investment-mindset-and-risk-control.md
│   │   ├── macro-cycle-and-asset-allocation.md
│   │   └── apple-and-consumer-electronics.md
│   └── episodes/                           # EP0001.md ~ EP0690.md 雙層觀念筆記 (.md 與 .full.md)
│
├── docs/                                   # 系統架構規格與決策紀錄
│   ├── adr/
│   │   ├── 0001-progressive-gooaye-skill.md # ADR：漸進式按需技能架構決策
│   │   └── 0002-hybrid-extractive-distilled-notes.md # ADR：雙層混合筆記架構決策
│   └── specs/                              # 系統規格書
│
├── scripts/                                # 安裝與自動化管理腳本
│   └── install-skill.sh                    # 一鍵安裝 / Symlink 技能腳本 (全域或指定專案)
│
├── .work/                                  # 數據處理、合成管道與品質稽核核心引擎
│   ├── cli.py                              # 統一命令列介面 (synthesize / audit / topics / doctor)
│   ├── domain.py                           # 核心領域物件 (EpisodeNote, Chapter, TopicGuide 等)
│   ├── episode_synthesizer.py              # 單集與全集批次並行合成調度器
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
如果您在當前 `gooaye-agent` 專案目錄下開啟 Antigravity，Agent 會自動偵測到 [`.agents/skills/gooaye/SKILL.md`](file:///Users/yuhan/coding/gooaye-agent/.agents/skills/gooaye/SKILL.md)，**無需任何安裝即可直接提問**。

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
# 1. 執行環境與數據源體檢
python3 .work/cli.py doctor

# 2. 執行全集 689 集標題與觀點品質審計
python3 .work/cli.py audit

# 3. 執行四大主題專題手冊品質審計
python3 .work/cli.py topics --audit

# 4. 批次全量合成主題專題指南
python3 .work/cli.py topics --generate

# 5. 批次多執行緒合成全集雙層 Markdown 筆記
python3 .work/cli.py synthesize --workers 8

# 6. 執行核心模組單元測試套件
pytest .work/
```

### 相關架構文件
- [CONTEXT.md](file:///Users/yuhan/coding/gooaye-agent/CONTEXT.md)：核心領域概念、深模組介面與品質閘門標準。
- [ADR 0001](file:///Users/yuhan/coding/gooaye-agent/docs/adr/0001-progressive-gooaye-skill.md)：漸進式按需技能架構決策紀錄。
- [ADR 0002](file:///Users/yuhan/coding/gooaye-agent/docs/adr/0002-hybrid-extractive-distilled-notes.md)：雙層混合筆記架構決策紀錄。
- [主題專題目錄](file:///Users/yuhan/coding/gooaye-agent/gooaye-youtube-notes/topics/README.md)：四大主題專題手冊。
- [全集索引表](file:///Users/yuhan/coding/gooaye-agent/gooaye-youtube-notes/_index.md)：689 集完整章節索引。

---

## 📄 免責聲明 (Disclaimer)

- 本專案所有逐字稿與結構化筆記僅供學術研究、觀念索引與個人學習使用。
- 節目內容與 AI 產生之回覆均不構成任何形式的投資建議或買賣推薦。
