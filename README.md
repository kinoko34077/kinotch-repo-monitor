# KiNoTch. Repo Monitor

複数のChatGPT通常チャットでリポジトリを並行編集している時に、ローカルGitの活動状況とdevflow上の開発工程をブラウザ上のカードで一覧する軽量localhost Webアプリです。

## できること

- `~/Documents/Programs`（Windowsでは通常 `%USERPROFILE%\Documents\Programs`）直下のGit repoを自動検出
- scan root外のGit repoも絶対パスを入力して手動追加
- 画面幅に合わせて自動変形するレスポンシブカード表示
- 名前・branch・path・devflow状態を検索
- ローカル状態を `編集中 / 一時停止 / 停止中 / Commit済 / 待機 / エラー` で表示
- public `kinoko34077/devflow` の `[REPO]` Control Issueから、`Work Status / Repository State / Active Work / Next Action` を読取専用で表示
- devflow工程を `実装中 / レビュー待ち / ブロック / 監査済 / 保留` 等の別バッジで表示
- branch、short HEAD、変更ファイル数、最終活動、ahead/behindを表示
- ChatGPT URLを登録し、カードから直接開く
- URL編集、repoフォルダを開く、登録解除、再検出
- 同名フォルダのrepoが複数あってもパス単位で別repoとして扱う
- Git監視は最大4repoを並列に検査し、多数repo時の更新待ちを抑える
- devflow取得は2分キャッシュし、2秒ごとのローカル更新とは分離
- Python標準ライブラリ + Gitのみで動作し、Node/npmは不要

## 状態判定

### ローカル状態

`ACTIVE`は「ChatGPTが現在生成中」という意味ではなく、変更ファイルのmtimeが直近60秒以内であることを示します。Gitとファイルシステムから観測できないChatGPT内部状態は推測しません。

- 緑 `編集中`: dirty + 60秒以内に変更
- 黄 `一時停止`: dirty + 10分以内
- 橙 `停止中`: dirty + 10分超
- 青 `Commit済`: clean + upstreamよりahead
- 灰 `待機`: clean
- 赤 `エラー`: Git読取失敗

### devflow工程

devflow側は各repositoryのopen `[REPO] <repository>` Control Issueを読み、ローカル状態とは別に表示します。

例:

- `IMPLEMENTING` → `実装中`
- `AWAITING_REVIEW` → `レビュー待ち`
- `BLOCKED` → `ブロック`
- `AUDITED` → `監査済`
- `PARKED` → `保留`

`IMPLEMENTING`はdevflow上の工程状態であり、「今この瞬間にChatGPTが生成中」という意味ではありません。短時間のsession/heartbeat検出はこの版の対象外です。

取得はpublic GitHub REST APIから読取専用で行い、既定では120秒キャッシュします。取得失敗時は、前回正常取得値があればそれをstaleとして維持し、ローカルGit監視は継続します。

## 起動

Python 3.11+ と Git が必要です。

PowerShell:

```powershell
.\run.cmd
```

cmd.exe:

```bat
run.cmd
```

通常は `http://127.0.0.1:17341/` でローカルサーバーを起動し、既定ブラウザを開きます。17341番portが使用中なら、空いているloopback portへ自動フォールバックします。外部ネットワークへ公開する用途ではありません。

ブラウザを自動で開かない場合:

```powershell
.\run.cmd --no-browser
```

別portを使う場合:

```powershell
.\run.cmd --port 18080
```

`run.cmd` は `python` → `py -3` → `python3` の順に、実際に起動可能なPython 3.11+を選びます。Windows Python Launcherに古いAnaconda登録が残っていても、別の有効なPythonがあればそちらへフォールバックします。

## Web UI

- カード一覧は画面幅に応じて自動的に列数が変わります。
- `Repo検索`で名前・branch・path・devflow工程を絞り込めます。
- 状態selectでローカル活動状態を絞り込めます。
- devflow管理対象では、ローカル状態バッジの下に工程状態と `Repository State / Active Work / Next Action` を表示します。
- Control Issue番号からdevflow Issueを開けます。
- `Repo追加`でscan root外のローカルGit repoを絶対パスから登録できます。
- `Chatを開く / Chat登録`でChatGPT URLを利用します。
- `URL編集`でリンク変更、`フォルダ`でローカルrepoを開きます。
- `解除`はconfig上の登録を外すだけで、自動検出対象なら再検出すると復帰します。

ブラウザのセキュリティ制約により、Web版の`Repo追加`はネイティブのフォルダ選択ダイアログではなく絶対パス入力方式です。backend側で `.git` の存在を検証します。

## 設定保存先

Windows: `%APPDATA%\KiNoTchRepoMonitor\config.json`

ここにscan root、repo path、ChatGPT URLを保存します。repo内へ個人URLは保存しません。設定は同一ファイルシステム上の一時ファイルからatomic replaceし、破損JSONを検出した場合は `config.json.corrupt` へ退避して既定値で起動します。

## 検証

PowerShell:

```powershell
.\verify.cmd
```

`verify.cmd` はunit tests、compile check、headless smoke、localhost Web render/fetch checkを、`run.cmd`と同じPython選択規則で実行します。GitHub ActionsではEdge/Chrome系headless browserで実際にlocalhost UIを描画し、screenshot artifactも生成します。

## Repository Base / devflow

- `project/` はlocal Web surfaceとして構成しています。
- devflowは開発運用上のcross-repository authorityであり、runtimeではpublic Control Issueを読取専用の工程表示にも利用します。
- ローカル活動状態の正本はGit/filesystem観測で、devflow工程状態とは混同しません。
- runtimeへmanaged-repository一覧は埋め込みません。
- 初期実装ではローカルrepoのbasenameとdevflow `[REPO]` 名を大文字小文字を無視して対応付けます。

## GitHub

このプロジェクトの正規リポジトリは `kinoko34077/kinotch-repo-monitor` です。

```powershell
git clone https://github.com/kinoko34077/kinotch-repo-monitor.git
cd kinotch-repo-monitor
.\run.cmd
```
