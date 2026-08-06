# Trusted Advisor のアラートを Slack に通知するアーキテクチャ

## こういう場面で困る

Trusted Advisor は「コンソールを開いた人しか気づかない」サービス。公開設定になった S3 バケットや漏洩したアクセスキーをチェックが検出して WARN / ERROR になっていても、誰かが見に行くまで放置される。月イチの棚卸しで開いて「これいつから赤かったんだ」となるのが典型的な失敗パターン。

だから Slack に流したくなる。ただし「EventBridge で全部 Slack に流す」という素朴な構成は、動くけれど 1〜2 週間でチャンネルごとミュートされて終わる。先にその理由から書く。

## 素朴な構成がなぜ破綻するか

Trusted Advisor は EventBridge（us-east-1 のみ）に `Trusted Advisor Check Item Refresh Notification` というイベントを流せる。これをそのまま SNS → Slack に繋ぐ構成が定番として紹介されがちだが、イベントの実際の挙動を見ると問題が分かる。

**イベントはチェック単位ではなく、チェック項目＝リソース単位で出る。** 公式のイベント例を見ると、`detail.check-item-detail` に個別リソースの情報（どのアクセスキーが、どの SG が）が入っていて、フラグが立ったリソース 1 件につき 1 イベントになる。つまり：

- **初回に爆発する**。運用歴のあるアカウントで有効化した直後のリフレッシュで、既存の指摘事項（開いた SG が 30 個あれば 30 イベント）が一斉に Slack に流れ込む
- **再通知を止める仕組みがない**。「ステータスが変化した時だけイベントが出る」という保証はドキュメントのどこにも書かれていない。イベント名は「Refresh Notification（リフレッシュ通知）」であり、EventBridge は at-least-once 配信。同じリソースの同じ WARN が週次リフレッシュのたびに再通知される前提で設計する必要がある
- **フラッピングを増幅する**。サービスリミット使用率が 80% 前後を行き来するようなチェックは、WARN ↔ OK を往復するたびにイベントを出す

要するに、リソース単位のイベントをそのまま人間のチャンネルに流すのは、通知の粒度と人間の行動の粒度が合っていない。

### 「ベストエフォート配信」をどう扱うか

もうひとつ、Trusted Advisor の EventBridge への発行は公式に「ベストエフォート」と分類されている。これは「頻繁に落ちる」という意味ではない（実運用で体感できるほど落ちる報告はほぼない）。問題は確率ではなく、**発行されなかったイベントには痕跡がなく、落ちたことを検知する手段がゼロ**なこと。リトライもなければ突合できる受領記録もないので、「来なかった ERROR」は完全なサイレント故障になる。

さらに現実には、取りこぼしの主犯は AWS 側の発行漏れより自分のパイプライン側にある。EventBridge ルールの書き間違い、Lambda のバグ、KMS ポリシー漏れ、Chatbot の紐付けミス——どれも通知が黙って消える。

結論はこう整理できる：**通知はイベント駆動でいい。ただし「見逃しがない」という統制はイベント駆動に置かず、定期ポーリングで担保する**。ポーリングがあれば、どんな取りこぼしも「最大 1 周期遅れで必ず拾う」という上限を作れる。

## 理想状態の定義：どういう場合に、どのくらいの通知か

アラート疲れを防ぐ原則はひとつ。**即時通知は「人が対応すべき新規の検出」だけに絞り、再通知は意図したリマインドとしてだけ行い、それ以外は定期ダイジェストに集約する。**

| レーン | 対象 | 頻度の理想 | 判断基準 |
|---|---|---|---|
| 即時通知 | セキュリティ系チェックの WARN / ERROR の**新規検出** | 新規発生時のみ。平常時は静か | 対応が必要な変化か？ |
| リマインド | 未解消のまま N 日経過したセキュリティ項目 | 解消されるまで N 日ごと（例：3 日） | 放置を検出できるか？ |
| 定期ダイジェスト | 上記以外すべて（コスト、耐障害性など） | **週 1 通に固定** | 棚卸しのインプットになるか？ |
| 通知しない | 変化のない項目のリフレッシュ再通知、OK 復帰のリソース単位通知 | 0 | 解消はダイジェストの「解消 N 件」で見る |

ポイントは再通知を「事故」ではなく「設計されたリマインド」にすること。同じ項目の通知が来るのは、リフレッシュのたびのランダムな重複ではなく「N 日経っても未解消」という意味を持ったときだけ。リマインドが増えてきたらそれ自体が「対応が回っていない」というシグナルになる。リスク受容した項目は Trusted Advisor ネイティブの除外（exclusion）に落としてリマインド対象から外し、自前で持つのは除外の期限管理だけにする（無期限の受容は作らない。期限が来たら include に戻して受容の再評価を強制する）。

ダイジェストは「新規 N 件 / 解消 M 件 / 継続 K 件」の 1 通に集約し、来る曜日を固定する。人間は「毎週月曜朝に来る 1 通」は読むが、「ランダムに来る 30 通」は読まない。

## この理想を実現するアーキテクチャ

```
【即時レーン】セキュリティ系チェックの WARN/ERROR・新規のみ
Trusted Advisor
  → EventBridge（us-east-1）: セキュリティ系チェック名 + status で絞る
    → Lambda: DynamoDB の通知台帳と照合 → 新規だけ整形して Slack へ
              （既知の項目は台帳の最終確認日時を更新するだけ）

【定期レーン】リマインド＋週次ダイジェスト＋取りこぼし補完
EventBridge Scheduler（日次）
  → Lambda: Trusted Advisor API で全チェック結果を取得
    ├ 未解消のセキュリティ項目が N 日経過 → リマインド再通知
    ├ 台帳にない WARN/ERROR を発見 → イベント取りこぼしとして即通知＋台帳登録
    ├ 台帳にあるが解消済み → 台帳クローズ（週次ダイジェストの「解消」に計上）
    └ 週 1 回: 全体差分「新規/解消/継続」を 1 通に集約して Slack へ
```

リマインドを即時レーン側（イベントの再送頼み）に置かないのが要点。イベントの再送はベストエフォートで保証がないので、「N 日ごとに必ず来る」を保証できるのはスケジュール駆動の側だけ。

### 即時レーンのイベントパターン

イベントの `detail` にはカテゴリ情報がないため、セキュリティ系はチェック名の列挙で絞る。

```json
{
  "source": ["aws.trustedadvisor"],
  "detail-type": ["Trusted Advisor Check Item Refresh Notification"],
  "detail": {
    "status": ["ERROR", "WARN"],
    "check-name": [
      "Exposed Access Keys",
      "Amazon S3 Bucket Permissions",
      "Security Groups - Specific Ports Unrestricted",
      "Security Groups - Unrestricted Access"
    ]
  }
}
```

### 通知台帳（DynamoDB）の設計

主キーは新 Trusted Advisor API の **recommendation resource ARN** に一本化する。EventBridge イベントは旧 Support API 系の ID 空間（`uuid` / `resource_id` / `check-item-detail`）で ARN を直接は持っていないが、チェック ID を介して辿れる：

1. イベントの `check-name` → `checkArn`（`arn:aws:trustedadvisor:::check/<チェックID>`。新 API の `ListChecks` が名前と ARN を返す。対象チェックは数個なのでキャッシュで足りる）
2. `ListRecommendations(checkIdentifier=checkArn)` → `recommendationArn`
3. `ListRecommendationResources(recommendationArn)` → 該当リソースを特定して resource ARN を得る。`awsResourceId` があればそれで照合、無いチェックはイベントの `check-item-detail` と API 側の `metadata`（同じ列スキーマ由来）を識別列で照合する（`Time Updated` のような揮発列は照合に使わない）

ARN に正規化する利点は、即時通知・リマインド・解消判定・除外操作（`BatchUpdateRecommendationResourceExclusion` は ARN を受け取る）が全部同じキーで回ること。台帳の属性には初回検出日時・初回通知日時・最終リマインド日時・状態（未解消 / 解消 / 受容と期限）を持つ。

- **即時レーン**は台帳にない項目だけ通知する。これで at-least-once の重複・リフレッシュごとの再イベント・フラッピングをまとめて吸収できる
- **解決のフォールバック**：イベント到着直後は新 API 側に同じリフレッシュ結果がまだ反映されていないことがありうる。ARN 解決に失敗したら数分後にリトライし、それでもダメなら「チェック + 抽出した識別子」で仮登録して通知だけ先に出し、定期レーンが次回実行時に ARN へ補正する
- **リマインド**は定期レーンが台帳を見て「未解消かつ最終通知から N 日経過」を再通知する
- **導入時のベースライン取り込み**を忘れない。有効化前に定期レーンを 1 回流して既存の指摘を台帳に「通知済み」として登録しておけば、初回爆発はゼロになる。既存分は初回の週次ダイジェストで「継続 K 件」として一覧で見る

なお resource の ID がリフレッシュをまたいで同一である保証は明文化されていないので、定期レーンでは `awsResourceId` ベースで重複エントリを潰す処理を入れておくと堅い。

### まず小さく始めるなら

いきなり全部作る必要はない。**最初の 1 歩は即時レーンだけ・チェック名 2〜3 個**でいい。SNS + Amazon Q Developer in chat applications（旧 AWS Chatbot）に直結すればコードゼロで動く（整形・重複排除・リマインドは諦める）。重複がうるさくなったら台帳を、放置が気になったら定期レーンを足す。逆に「まず全部流して様子を見る」は、チャンネルの信頼を初日に使い切るのでやらない。

なお EventBridge のリファレンスには Trusted Advisor のダイジェスト系 detail-type（`Trusted Advisor Pursuit Weekly Digest` / `Daily Digest`）も追加されている。内容のカスタマイズや差分計算はできないが、要件が緩ければ自前 Lambda の代わりにまず試す価値はある。

## 前提条件とハマりどころ

- **Business / Enterprise On-Ramp / Enterprise のサポートプランが必要**。Basic / Developer ではチェック自体がほぼ動かない
- **EventBridge ルールと SNS トピックは必ず us-east-1 に作る**。Trusted Advisor はグローバルサービスで、イベントは us-east-1 にしか流れない。ap-northeast-1 にルールを作って「何も来ない」で数時間溶かすのが定番のハマり方
- **チェックの自動リフレッシュは週次程度**。「発生した瞬間」ではなく「リフレッシュで検出された瞬間」の通知。間隔を詰めたければ `RefreshTrustedAdvisorCheck` API の定期実行（最短 5 分間隔）で短縮できるが、リアルタイム検知が本当の要件なら AWS Config ルールや GuardDuty の領分。Trusted Advisor 通知は「定期健診の結果を、見に行かなくても届くようにする」ものと位置づける
- SNS トピックを KMS 暗号化している場合、キーポリシーで EventBridge からの発行を許可する（これも無通知でハマる）

## 提案するときの言い方

> Trusted Advisor は AWS が自動でやってくれる設定診断だが、結果は誰かが見に行かないと気づけない。これを「セキュリティの指摘は即時に、直るまで数日ごとに催促、それ以外は週 1 のサマリで」Slack に届くようにする。全部流すのではなく通知量を設計するので、アラート疲れで形骸化しないし、放置も自動で検出される。追加コストは Lambda と DynamoDB でほぼゼロ（サポートプランは既存契約の範囲）。

## 参考

- [Monitoring AWS Trusted Advisor check results with Amazon EventBridge - AWS Support](https://docs.aws.amazon.com/awssupport/latest/user/cloudwatch-events-ta.html)
- [AWS Trusted Advisor events - Amazon EventBridge](https://docs.aws.amazon.com/eventbridge/latest/ref/events-ref-trustedadvisor.html)
- [AWS Trusted Advisor - AWS Support](https://docs.aws.amazon.com/awssupport/latest/user/trusted-advisor.html)
- [Trusted Advisor API Reference（ListRecommendations 等）](https://docs.aws.amazon.com/trustedadvisor/latest/APIReference/Welcome.html)
- [ListRecommendationResources - AWS Trusted Advisor API](https://docs.aws.amazon.com/trustedadvisor/latest/APIReference/API_ListRecommendationResources.html)
- [How to exclude resources from AWS Trusted Advisor reports using Trusted Advisor API - AWS re:Post](https://repost.aws/articles/AR2RklKWyrTRGTCaZZu11dPw/how-to-exclude-resources-from-aws-trusted-advisor-reports-using-trusted-advisor-api)
- [RefreshTrustedAdvisorCheck - AWS Support API Reference](https://docs.aws.amazon.com/awssupport/latest/APIReference/API_RefreshTrustedAdvisorCheck.html)
- [Tutorial: Get started with Slack - Amazon Q Developer in chat applications](https://docs.aws.amazon.com/chatbot/latest/adminguide/slack-setup.html)
- [aws/Trusted-Advisor-Tools（ExposedAccessKeys のイベント例）- GitHub](https://github.com/aws/Trusted-Advisor-Tools/blob/master/ExposedAccessKeys/README.md)
- [aws-samples/aws-trusted-advisor-scheduled-refresh - GitHub](https://github.com/aws-samples/aws-trusted-advisor-scheduled-refresh)
