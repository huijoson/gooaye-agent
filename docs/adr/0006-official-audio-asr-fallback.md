---
status: accepted
date: 2026-09-24
---

# Official audio ASR for missing transcripts

EP694–EP699 已有官方節目音訊，第三方逐字稿仍缺漏。依使用者明確要求，以官方 SoundOn RSS enclosure 音訊進行本機 MLX Whisper large-v3-turbo 轉錄，允許標示來源的 ASR Transcript 納入 Episode Source Snapshot；此決策取代 ADR 0003 對「第三方逐字稿缺漏時不得生成替代稿」的限制，預設 `download` 的來源檢查仍保留。

音訊與集數須由官方 RSS 對齊；來源快照保留來源 URL；`.work/asr-transcripts/EPxxxx.json` 保留音訊 SHA-256、模型版本、轉錄時間及分段時間證據。ASR 與衍生筆記均標示尚未人工校對，避免將模型誤聽當成精確原話；需要確認實體名詞、數字或措辭時回查原音。完整性與 Manifest 驗證只證明資料結構和內容一致，不能證明轉錄正確。

ASR 來源沿用既有冷封存與交易式發布邊界；後續第三方稿或人工校訂可透過顯式來源取代及重新發布更新。原始音訊與模型檔不納入正式知識庫。
