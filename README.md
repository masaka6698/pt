# PTT PttEarnMoney → Discord 通知

每 5 分鐘由 GitHub Actions 檢查：

- https://www.ptt.cc/bbs/PttEarnMoney/index.html
- 發現新的文章 ID 時，透過 Discord Incoming Webhook 發送通知。
- 第一次執行只記錄目前文章，不通知既有舊文。
- `data/seen_posts.json` 由 GitHub Actions 自動提交，避免下一次重複通知。

## 1. 建立 Discord Webhook

1. 到 Discord 伺服器中選擇接收通知的文字頻道。
2. 開啟「編輯頻道」→「整合」→「Webhook」。
3. 建立 Webhook，複製 Webhook URL。
4. Webhook URL 等同密碼，不要放進 Python 程式或公開 Repository。

## 2. 建立 GitHub Repository

建立一個新的 GitHub Repository，建議設為 **Private**。

把本專案的所有檔案上傳，資料夾結構需保持如下：

```text
.
├── .github/
│   └── workflows/
│       └── monitor.yml
├── data/
│   └── seen_posts.json
├── .gitignore
├── ptt_monitor.py
├── requirements.txt
└── README.md
```

## 3. 新增 GitHub Secret

Repository 頁面：

1. `Settings`
2. `Secrets and variables`
3. `Actions`
4. `New repository secret`
5. Name 填：`DISCORD_WEBHOOK_URL`
6. Secret 貼上 Discord Webhook URL

## 4. 允許 GitHub Actions 寫回狀態檔

Repository 頁面：

1. `Settings`
2. `Actions`
3. `General`
4. 找到 `Workflow permissions`
5. 選 `Read and write permissions`
6. 儲存

工作流程本身也已設定：

```yaml
permissions:
  contents: write
```

## 5. 手動測試第一次執行

1. 進入 Repository 的 `Actions`
2. 點選 `Monitor PTT PttEarnMoney`
3. 點 `Run workflow`

第一次成功時，Discord 預設不會收到舊文章通知；GitHub 會更新
`data/seen_posts.json`。之後只要額板出現新文章就會通知。

## 6. 想測試 Discord 通知

暫時把 `.github/workflows/monitor.yml` 的：

```yaml
NOTIFY_ON_FIRST_RUN: "false"
```

改成：

```yaml
NOTIFY_ON_FIRST_RUN: "true"
```

並把 `data/seen_posts.json` 改回：

```json
{
  "initialized": false,
  "seen_ids": []
}
```

再手動執行一次。測試完請改回 `false`，否則第一次會把目前頁面的文章全部通知。

## 注意事項

- GitHub Actions 排程的最短間隔是 5 分鐘，而且繁忙時可能延遲，不是即時推播。
- 本程式只監看最新列表頁。若在兩次檢查間出現大量文章，多到文章已離開最新頁面，可能漏掉；一般看板流量通常不至於在 5 分鐘內發生。
- 若 PTT 修改 HTML 結構，程式會因抓不到文章而失敗，避免錯誤覆寫狀態。
- GitHub 可能停用長期無活動 Repository 的排程工作流程；可定期確認 Actions 是否仍啟用。
