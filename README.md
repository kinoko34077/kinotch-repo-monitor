# KiNoTch. Repo Monitor

複数のChatGPT通常チャットでリポジトリを並行編集している時に、ローカルGitの活動状況をブラウザ上のカードで一覧する軽量localhost Webアプリです。

## できること

- `~/Documents/Programs`（Windowsでは通常 `%USERPROFILE%\Documents\Programs`）直下のGit repoを自動検出
- 画面幅に合わせて自動変形するレスポンシブカード表示
- 名前・branch・path検索と状態フィルター
- 色 + 状態名で `編集中 / 一時停止 / 停止中 / Commit済 / 待機 / エラー` を表示
- branch、short HEAD、変更ファイル数、最終活動、ahead/behindを表示
- ChatGPT URLを登録し、カードから直接開く
- URL編集、repoフォルダを開く、登録解除、再検出
- 同名フォルダのrepoが複数あってもパス単位で別repoとして扱う
- Git監視は最大4repoを並列に検査し、多数repo時の更新待ちを抑える
- Python標準ライブラリ + Gitのみで動作し、Node/npmは不要

## 状態判定

`ACTIVE`は「ChatGPTが現在生成中」という意味ではなく、変更ファイルのmtimeが直近60秒以内であることを示します。Gitとファイルシステムから観測できないChatGPT内部状態は推測しません。

- 緑 `編集中`: dirty + 60秒以内に変更
- 黄 `一時停止`: dirty + 10分以内
- 橙 `停止中`: dirty + 10分超
- 青 `Commit済`: clean + upstreamよりahead
- 灰 `待機`: clean
- 赤 `エラー`: Git読取失敗

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

通常は `http://127.0.0.1:17341/` でローカルサーバーを起動し、既定ブラウザを開きます。外部ネットワークへ公開する用途ではありません。

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
- `Repo検索`で名前・branch・pathを絞り込めます。
- 状態selectで活動状態を絞り込めます。
- `Chatを開く / Chat登録`でChatGPT URLを利用します。
- `URL編集`でリンク変更、`フォルダ`でローカルrepoを開きます。
- `解除`はconfig上の登録を外すだけで、再検出すると復帰します。

## 設定保存先

Windows: `%APPDATA%\KiNoTchRepoMonitor\config.json`

ここにscan root、repo path、ChatGPT URLを保存します。repo内へ個人URLは保存しません。設定は同一ファイルシステム上の一時ファイルからatomic replaceし、破損JSONを検出した場合は `config.json.corrupt` へ退避して既定値で起動します。

## 検証

PowerShell:

```powershell
.\verify.cmd
```

`verify.cmd` はunit tests、compile check、headless smoke、localhost Web render/fetch checkを、`run.cmd`と同じPython選択規則で実行します。

## Repository Base / devflow

- `project/` はlocal Web surfaceとして構成しています。
- devflowは開発運用上のcross-repository authorityとして使用し、アプリruntimeへmanaged-repository一覧を埋め込みません。
- GUIに表示するrepoはローカル検出・登録状態だけを正とします。

## GitHub

このプロジェクトの正規リポジトリは `kinoko34077/kinotch-repo-monitor` です。

```powershell
git clone https://github.com/kinoko34077/kinotch-repo-monitor.git
cd kinotch-repo-monitor
.\run.cmd
```
