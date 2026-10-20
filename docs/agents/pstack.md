# 在 Codex 使用 pstack

此專案安裝 [cursor/plugins 的 pstack](https://github.com/cursor/plugins/tree/88d47514b82e7c44f00f2b2a72ff6dd12158038c/pstack)，固定版本為 `88d47514b82e7c44f00f2b2a72ff6dd12158038c`。

在 Codex 輸入：

```text
$poteto-mode 調查這個問題，先重現，再修正與驗證。
$how 解釋 Episode Source Repository 如何選擇來源。
$interrogate 檢查這次修改。
$setup-pstack 設定這個專案的模型角色。
```

下一輪即可使用；若技能選單未更新，重新啟動 Codex。專案技能目錄與 symlink 支援見 [OpenAI 官方技能文件](https://learn.chatgpt.com/docs/build-skills)。

上游共有 56 個技能，實體放在 [`.agents/vendor/pstack/`](../../.agents/vendor/pstack/)，由 `.agents/skills/` 的相對 symlink 提供 Codex 探索。既有 `tdd`、`teach` 保留，上游版本分別以 `$pstack-tdd`、`$pstack-teach` 呼叫。

這是本專案的 Codex 適配版本。工具與模型對應見 [Codex adapter](../../.agents/vendor/pstack/docs/harness/codex.md)。所有角色預設沿用目前模型；需要調整時使用 `$setup-pstack`，設定寫入 `.agents/pstack-models.md`。Cursor Automations、雲端代理及未提供的外部工具仍需各自整合。

本地變更包含：技能開頭的 adapter 指引、Codex 支援的 frontmatter、保留上游手動呼叫語意的 `agents/openai.yaml`、兩個名稱衝突的處理，以及 Codex 版 `setup-pstack`。上游 setup 原文保留於 `docs/harness/setup-pstack-cursor.md`。更新上游時須重新套用這些適配，並驗證 symlink 與技能格式。上游 MIT 授權保留於 bundle 的 `LICENSE`。
