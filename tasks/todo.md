# 2026-09-24 更新缺少的股癌集數

## 驗收條件
- 比對官方最新集數、第三方逐字稿與本地 EP1–EP693，補齊來源完整的缺集。
- 成功取得的集數同步冷封存、雙層筆記與索引；來源未齊全則明確記錄。
- 正式發布 Manifest 與主題連結驗證通過。

## 計畫
- [x] 檢查現有資料與基線驗證（693 集、1393 artifacts、0 defects）。
- [x] 查核即時上游與缺集：YouTube / SoundOn 均有 EP694–EP699，archive 最大集數為 693。
- [x] 無可取得的新集數；EP694–EP699 全部 archive pending，未執行重新發布。
- [x] 更新 README 與冷封存追蹤狀態；Manifest、主題連結與全集連續性驗證通過。

## 風險與回復
- 低風險資料更新；沿用三方來源對齊與交易式 publish，不強制覆寫既有來源。
- 上游缺逐字稿時保留現有完整發布，不以摘要冒充逐字稿。

## 環境與工作筆記
- Python 3；上游 YouTube RSS、SoundOn RSS、whatmkreallysaid.com。
- tasks/lessons.md 原不存在；工作區起始乾淨。
- download --latest 只針對最新一集，不會回補全部缺集。

## 結果
- `download --latest` 回報 `EP699 is not present in the archive index`，未寫入 snapshot。
- 本地逐字稿、導航筆記與深度筆記均完整涵蓋 EP1–EP693。
- 更新 README.md 與 transcripts/README.md 的官方進度、缺集範圍和逐集補齊指令。
- `doctor` 全數通過；`verify`：693 集、1393 artifacts、0 defects；`topics --audit`：4 份、0 defects。
- 沒有程式碼變更；未跑單元測試，以資料完整性與發布驗證為準。
- 後續：第三方逐字稿釋出後重試缺集下載，再執行 publish。

# 2026-09-24 直接轉錄 EP694–EP699（使用者追加授權）
- [x] 取得六集官方 SoundOn 音訊（YouTube 媒體端回傳 403），用本機 Whisper 轉錄。
- [x] 加入明確 ASR 來源、模型與音訊雜湊，保留時間戳及原始辨識結果。
- [x] 匯入六集、同步封存、校對章節快取並交易式發布。
- [x] 驗證音訊時長與辨識覆蓋、來源完整性、測試、Manifest 與主題連結。

工作筆記：六集音訊合計約 5 小時；ASR JSON 時間戳涵蓋全段。官方 RSS metadata 日期與片長與下載音訊吻合。開場業配截點逐集人工定位，只影響筆記摘錄；冷封存保留全稿。
驗收：EP1–EP699 完整；EP694–699 明確標示機器轉錄且未逐字人工校對，不冒稱第三方逐字稿。
風險：ASR 專有名詞可能誤辨；保留原始結果供回查。既有 snapshot 不強制覆寫，正式發布沿用交易式替換。

## 最終結果
- EP694–EP699 來自官方 SoundOn RSS 音訊，MLX Whisper large-v3-turbo 轉錄；`.work/asr-transcripts/` 留存原始分段、模型版本與雜湊，`transcripts/` 保留六集完整轉錄與未人工校對標示。
- 六集共 48 章；目前正式發布 EP1–EP699、5,376 章、約 550.5 小時，1405 個 Manifest artifacts。
- `python3 -m pytest .work/ -q`：285 passed、2 skipped。
- `python3 .work/cli.py verify --output-dir gooaye-youtube-notes`：699 episodes、4 topics、0 defects；`topics --audit` 與六集 `audit` 均 0 defects；`doctor` 通過。
- 冷封存、導航與深度筆記均連續 EP1–EP699；六集 ASR 時間戳涵蓋音訊首尾，快照來源 URL 可跨裝置使用。
- 聽寫與專有名詞未經逐句人工校音；精確引言應回聽官方音訊。

# 2026-09-26 上傳最新版本至 GitHub
- 驗收：EP1–EP699 與 ASR 來源程式、證據及文件提交至 origin/main，遠端 commit 與本地一致。
- [x] 確認變更、遠端與分支；fetch origin。
- [x] 執行測試、發布驗證與主題審計。
- [x] 檢查提交檔案（獨立審查無阻擋問題）。
- [x] commit 並 push；核對遠端。
- 風險與回復：沿用既有發布結果；若需回復，以 revert 本次 commit 處理，不改寫歷史。

驗證結果：pytest 285 passed / 2 skipped；verify 699 episodes / 1405 artifacts / 0 defects；topics --audit 0 defects；doctor 通過；git diff --check 與新增檔案 secret-pattern scan 通過。

上傳結果：版本提交 `26348ee` 已推送至 origin/main，git ls-remote 與本地 HEAD 一致。
