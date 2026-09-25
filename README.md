# KiNoTch. Repo Monitor

複数のChatGPT通常チャットでリポジトリを並行編集している時に、ローカルGitの活動状況を5列カードで一覧する軽量Windows GUIです。

## できること

- `~/Documents/Programs`（Windowsでは通常 `%USERPROFILE%\Documents\Programs`）直下のGit repoを自動検出
- 5列 × 下段追加のカード表示
- 色 + 状態名で `編集中 / 一時停止 / 停止中 / Commit済 / 待機 / エラー` を表示
- branch、short HEAD、変更ファイル数、最終活動、ahead/behindを表示
- カードにChatGPT URLを登録し、次回からカードクリックで直接開く
- 右クリックでURL編集、repoフォルダを開く、一覧から削除

## 状態判定

`ACTIVE`は「ChatGPTが現在生成中」という意味ではなく、変更ファイルのmtimeが直近60秒以内であることを示します。Gitとファイルシステムから観測できないChatGPT内部状態は推測しません。

- 緑 `編集中`: dirty + 60秒以内に変更
- 黄 `一時停止`: dirty + 10分以内
- 橙 `停止中`: dirty + 10分超
- 青 `Commit済`: clean + upstreamよりahead
- 灰 `待機`: clean
- 赤 `エラー`: Git読取失敗

## 起動

Python 3.11+ と Git が必要です。公式Windows版PythonであればTkinterは通常同梱されています。

```bat
run.cmd
```

または:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3 -m repo_monitor
```

初回は検出されたrepoがカード化されます。Chat URL未登録のカードをクリックするとURL入力が出るので、ブラウザで開いている通常チャットのURLを貼り付けます。

## 設定保存先

Windows: `%APPDATA%\KiNoTchRepoMonitor\config.json`

ここにscan root、repo path、ChatGPT URLを保存します。repo内へ個人URLは保存しません。

## 検証

```bat
verify.cmd
```

## Repository Base / devflow

- `project/` は `kinotch-repository-base` の `windows-gui` profileに合わせた構造です。
- devflowの2026-09-25時点の30 managed repositoriesを並び順メタデータとして同梱しています。
- devflow自体のCurrent Stateを置き換えるものではありません。このGUIはローカル観測専用です。

## GitHub

このプロジェクトの正規リポジトリは `kinoko34077/kinotch-repo-monitor` です。

```powershell
git clone https://github.com/kinoko34077/kinotch-repo-monitor.git
cd kinotch-repo-monitor
run.cmd
```
