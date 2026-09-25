# KiNoTch. Repo Monitor

複数のChatGPT通常チャットでリポジトリを並行編集している時に、ローカルGitの活動状況を5列カードで一覧する軽量Windows GUIです。

## できること

- `~/Documents/Programs`（Windowsでは通常 `%USERPROFILE%\Documents\Programs`）直下のGit repoを自動検出
- 5列 × 下段追加のカード表示
- 色 + 状態名で `編集中 / 一時停止 / 停止中 / Commit済 / 待機 / エラー` を表示
- branch、short HEAD、変更ファイル数、最終活動、ahead/behindを表示
- カードにChatGPT URLを登録し、次回からカードクリックで直接開く
- 右クリックでURL編集、repoフォルダを開く、登録解除
- 同名フォルダのrepoが複数あってもパス単位で別repoとして扱う
- Git監視は最大4repoを並列に検査し、多数repo時の更新待ちを抑える

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

PowerShell:

```powershell
.\run.cmd
```

cmd.exe:

```bat
run.cmd
```

`run.cmd` は `python` → `py -3` → `python3` の順に、実際に起動可能なPython 3を選びます。Windows Python Launcherに古いAnaconda登録が残っていても、別の有効なPythonがあればそちらへフォールバックします。

初回は検出されたrepoがカード化されます。Chat URL未登録のカードをクリックするとURL入力が出るので、ブラウザで開いている通常チャットのURLを貼り付けます。

## 設定保存先

Windows: `%APPDATA%\KiNoTchRepoMonitor\config.json`

ここにscan root、repo path、ChatGPT URLを保存します。repo内へ個人URLは保存しません。設定は同一ファイルシステム上の一時ファイルからatomic replaceし、破損JSONを検出した場合は `config.json.corrupt` へ退避して既定値で起動します。

## 検証

PowerShell:

```powershell
.\verify.cmd
```

`verify.cmd` はunit tests、compile check、headless smokeを、`run.cmd`と同じPython選択規則で実行します。

## Repository Base / devflow

- `project/` は `kinotch-repository-base` の `windows-gui` profileに合わせた構造です。
- devflowは開発運用上のcross-repository authorityとして使用し、アプリruntimeへmanaged-repository一覧を埋め込みません。
- GUIに表示するrepoはローカル検出・登録状態だけを正とします。

## GitHub

このプロジェクトの正規リポジトリは `kinoko34077/kinotch-repo-monitor` です。

```powershell
git clone https://github.com/kinoko34077/kinotch-repo-monitor.git
cd kinotch-repo-monitor
.\run.cmd
```
