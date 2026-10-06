# KiNoTch. Repo Monitor

複数の開発repoを並行して扱う際に、ローカルGitの活動状況とdevflow上の開発工程をブラウザのカードで一覧する軽量localhost Webアプリです。

## GitHub Pages（read-only）

公開版: https://kinoko34077.github.io/kinotch-repo-monitor/

Pages版はpublic GitHub/devflow情報だけから生成する静的な読取専用dashboardです。repository workflow/audit状態とHuman Portfolioを外から確認できます。

Pages版には以下を含めません。

- ローカルfilesystem path
- ChatGPT URL
- local Gitのdirty / ahead / behind / activity状態
- local config
- credential / session
- mutation/write-back操作

ローカルGit監視、Chatリンク、Repo追加、再検出等が必要な場合は従来どおりlocalhost版を使用します。


## v0.5の要点

- `GET /api/state` はGitを走査せず、直近完了したローカルsnapshotを返します。
- Git走査は単一のbackground scan engineが所有し、repo内並列は最大8 workerです。
- scan要求が実行中に重なっても、後続は最大1回へcoalesceされます。
- ACTIVE/IDLEを含むscan完了後は既定2秒、静かな状態では5秒で次scanを行います。
- 初回scan前もHTTP/UIは利用でき、未観測repoは `確認中` (`PENDING`) と表示します。
- 通常refreshではrepoごとのDOM rootを保持し、focus・text selection・dialogの論理的な戻り先を維持します。
- cardの既定actionは `Chat` / `Repo` / `その他`。低頻度操作は `その他` にまとめます。
- `監視から外す` はrepo metadataとChatリンクを保持したまま一覧から外します。同じpathを明示的に再追加すると復帰します。
- devflowの折り畳み詳細にだけ存在する値へ検索一致した場合は、一致理由をcard上へ表示します。
- mutation中は起点controlをdisabledにし、同一actionの二重送信を抑止します。

## できること

- `%USERPROFILE%\Documents\Programs` 直下のGit repoを自動検出
- scan root外のGit repoを絶対pathで手動追加
- responsive card表示、名前・branch・path・devflow状態の検索、local status filter
- local statusを `編集中 / 一時停止 / 停止中 / Commit済 / 待機 / 確認中 / エラー` で表示
- public `kinoko34077/devflow` のopen `[REPO]` Control Issueから workflow stateを読取専用で取得
- devflow Controlは `OWNER` / `MEMBER` / `COLLABORATOR` のtrusted authorだけを採用し、PR lookalikeや重複trusted Controlはfail closed
- branch、short HEAD、変更数、最終活動、ahead/behindを表示
- ChatGPT URLの登録・直接open
- network Git remoteを正規化できる場合に `Repo` actionを表示
- folder open、再検出、manual refresh、monitoring removal
- Git inspectionではrepo側 `core.fsmonitor` を無効化し、ownership mismatchを `safe.directory` で強制回避しない
- ownershipがdubiousなrepoはGitの拒否理由を `エラー` として表示し、repo configを信頼状態へ格上げしない
- 同名repoをnormalized local path単位で区別
- Python標準ライブラリ + Gitのみで動作し、Node/npm・DB・常駐serviceは不要

## 状態判定

`ACTIVE`はChatGPT内部の生成状態ではなく、Git/filesystemから観測したlocal activityです。

- 緑 `編集中`: dirty + 最新変更mtimeが60秒以内
- 黄 `一時停止`: dirty + 10分以内、またはdirtyでmtime不明
- 橙 `停止中`: dirty + 10分超
- 青 `Commit済`: clean + upstreamよりahead
- 灰 `待機`: clean
- `確認中`: monitoring対象だが、まだ完了snapshotに観測結果がない
- 赤 `エラー`: Git inspection失敗

## devflow工程

devflow stateはlocal activityとは別レイヤです。`IMPLEMENTING`等は開発工程を表し、ChatGPTが今この瞬間に生成中であることは示しません。

既定ではpublic GitHub REST APIを120秒cacheし、backgroundで更新します。取得失敗時は前回正常値をstaleとして維持し、local monitoringは継続します。Control候補はtrusted author associationだけを採用し、pull request objectは無視します。同一repo名のtrusted Controlが複数ある場合はlast-winsにせずrefreshを失敗扱いにして、前回正常snapshotがあればstaleとして維持します。

## scan / refresh

ブラウザは既定2秒ごとにcached `/api/state` を読みます。このpolling自体はGit scanを起動しません。

Git scanを要求するのは主に以下です。

- monitor起動後の初回scan
- `更新` (`POST /api/refresh`)
- 新しいrepoの手動追加
- 再検出によりmonitoring対象path集合が変化した場合

Chat URL変更、folder open、`監視から外す`、変化のない再検出では不要なscanを要求しません。

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

通常は `http://127.0.0.1:17341/` を使い、既定browserを開きます。17341が使用中なら空いているloopback portへfallbackします。

browserを自動で開かない場合:

```powershell
.\run.cmd --no-browser
```

別port:

```powershell
.\run.cmd --port 18080
```

`run.cmd` は `python` → `py -3` → `python3` の順に、実行可能なPython 3.11+を選択します。

## Web UI

- `Repo検索`: repo情報とdevflow情報を検索。折り畳み内だけで一致した場合は `一致:` 理由を表示します。
- `状態`: local activity filter。
- `Repo追加`: scan root外repoを絶対pathから追加。
- `更新`: background Git scanを要求し、完了待ちでUIをblockしません。
- `再検出`: scan rootsを再探索。monitoring対象が変わった時だけscanを要求します。
- `Chatを開く / Chat登録`: ChatGPT URL。
- `Repo`: detected remote repository page。
- `その他`: `Chat URL編集` / `フォルダを開く` / `監視から外す`。

`監視から外す`は永続metadata削除ではありません。Chatリンクを保持し、同じpathを `Repo追加` するとmonitoringへ戻ります。

## Git remote / ownership trust

`origin`はlocal Gitから読取専用で取得し、HTTPS / SCP-like SSH / `ssh://` network remoteのみbrowser URLへ正規化します。`file://`、Windows local path、UNC/local absolute path、relative local pathはWeb link化しません。

各Git commandではprocess-localに `core.fsmonitor=false` と `GIT_OPTIONAL_LOCKS=0` を指定します。Repo Monitor自身は `safe.directory=<repo>` を注入しません。Gitがownership mismatchをdubious ownershipとして拒否した場合はその拒否をper-repository errorとして表示します。必要なtrust設定はGit側で利用者が明示的に管理する境界です。

## 設定保存先

Windows: `%APPDATA%\KiNoTchRepoMonitor\config.json`

scan roots、repo path、ChatGPT URL、monitoring membershipを保存します。writeはsame-filesystem temp file + `os.replace` のatomic replacementです。破損JSONは `config.json.corrupt` へ退避してdefaultsで起動します。

## 検証

```powershell
.\verify.cmd
```

GitHub Actionsではunit/regression、compile、launcher smoke、cached-state負荷試験、real browser interaction regression、Edge/Chrome headless renderとscreenshot artifactまで実行します。

主要な追加check:

```powershell
.\_run_python.cmd tools\benchmark_cached_state.py
.\_run_python.cmd tools\browser_interaction_check.py
```

## Repository Base / devflow

- `project/` はlocal Web surfaceです。
- devflowはcross-repository operational authorityで、runtimeではpublic Control Issueを読取専用表示します。
- local activityの正本はGit/filesystem観測で、devflow workflow stateとは混同しません。
- runtimeへmanaged repository一覧は埋め込みません。
- devflow overlayは、cached local Git remoteから得た正確なGitHub `owner/repo` とControl本文の `## Repository` が一致する場合だけ対応付けます。basenameだけでは対応付けません。

## GitHub

正規repositoryは `kinoko34077/kinotch-repo-monitor` です。

```powershell
git clone https://github.com/kinoko34077/kinotch-repo-monitor.git
cd kinotch-repo-monitor
.\run.cmd
```
