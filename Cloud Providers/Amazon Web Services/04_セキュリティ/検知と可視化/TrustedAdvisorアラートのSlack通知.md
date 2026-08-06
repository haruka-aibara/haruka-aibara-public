# Trusted Advisor のアラートを Slack に通知するアーキテクチャ

## こういう場面で困る

Trusted Advisor は「コンソールを開いた人しか気づかない」サービス。公開設定になった S3 バケットや漏洩したアクセスキーをチェックが検出して WARN / ERROR になっていても、誰かが見に行くまで放置される。月イチの棚卸しで開いて「これいつから赤かったんだ」となるのが典型的な失敗パターン。

だから Slack に流したくなる。ただし「EventBridge で全部 Slack に流す」という素朴な構成は、動くけれど 1〜2 週間でチャンネルごとミュートされて終わる。先にその理由から書く。

## 素朴な構成がなぜ破綻するか

Trusted Advisor は EventBridge（us-east-1 のみ）に `Trusted Advisor Check Item Refresh Notification` というイベントを流せる。これをそのまま SNS → Slack に繋ぐ構成が定番として紹介されがちだが、イベントの実際の挙動を見ると問題が分かる。

**イベントはチェック単位ではなく、チェック項目＝リソース単位で出る。** 公式のイベント例を見ると、`detail.check-item-detail` に個別リソースの情報（どのアクセスキーが、どの SG が）が入っていて、フラグが立ったリソース 1 件につき 1 イベントになる。つまり：

- **初回に爆発する**。運用歴のあるアカウントで有効化した直後のリフレッシュで、既存の指摘事項（開いた SG が 30 個あれば 30 イベント）が一斉に Slack に流れ込む
- **再通知を止める仕組みがない**。「ステータスが変化した時だけイベントが出る」という保証はドキュメントのどこにも書かれていない。イベント名は「Refresh Notification（リフレッシュ通知）」であり、しかも配信はベストエフォート・EventBridge は at-least-once 配信。同じリソースの同じ WARN が週次リフレッシュのたびに再通知される前提で設計する必要がある
- **フラッピングを増幅する**。サービスリミット使用率が 80% 前後を行き来するようなチェックは、WARN ↔ OK を往復するたびにイベントを出す
- **逆に、取りこぼしもある**。ベストエフォート配信なので、重大な ERROR のイベントが 1 件落ちても誰も気づけない。プッシュ通知だけの構成には「見逃しを検出する層」がない

要するに、リソース単位のイベントをそのまま人間のチャンネルに流すのは、通知の粒度と人間の行動の粒度が合っていない。

## 理想状態の定義：どういう場合に、どのくらいの通知か

アラート疲れを防ぐ原則はひとつ。**即時通知は「今すぐ人が動くべきもの」だけに絞り、それ以外は定期ダイジェストに集約する。**

| レーン | 対象 | 頻度の理想 | 判断基準 |
|---|---|---|---|
| 即時通知 | 漏洩アクセスキー、S3 公開、重要ポート開放などの ERROR | **月 0〜数件。0 が正常** | 深夜でも見たら動くか？ |
| 定期ダイジェスト | 上記以外すべて（コスト、耐障害性、WARN 全般） | **週 1 通に固定** | 棚卸しのインプットになるか？ |
| 通知しない | 継続中アイテムの再通知、OK 復帰のリソース単位通知 | 0 | 解消は ダイジェストの「解消 N 件」で見る |

即時レーンに週に何件も飛んでくるなら、それは通知設計の問題ではなく環境側の問題（そのくらい即時レーンは静かであるべき）。ダイジェストは「新規 N 件 / 解消 M 件 / 継続 K 件」の 1 通に集約し、来る曜日を固定する。人間は「毎週月曜朝に来る 1 通」は読むが、「ランダムに来る 30 通」は読まない。

## この理想を実現するアーキテクチャ

```
【即時レーン】ERROR かつ重大チェックのみ・重複排除つき
Trusted Advisor
  → EventBridge（us-east-1）: チェック名と status=ERROR で絞る
    → Lambda: DynamoDB で重複排除 → 整形して Slack へ

【ダイジェストレーン】週1で全体を突合（取りこぼしの補完を兼ねる）
EventBridge Scheduler（週1）
  → Lambda: Trusted Advisor API で全チェック結果を取得
    → 前回スナップショット（S3）と差分 → 1通に集約して Slack へ
```

### 即時レーンのイベントパターン

status だけでなくチェック名でも絞る。「ERROR 全部」は初回爆発とフラッピングの原因になる。

```json
{
  "source": ["aws.trustedadvisor"],
  "detail-type": ["Trusted Advisor Check Item Refresh Notification"],
  "detail": {
    "status": ["ERROR"],
    "check-name": [
      "Exposed Access Keys",
      "Amazon S3 Bucket Permissions",
      "Security Groups - Specific Ports Unrestricted"
    ]
  }
}
```

### 重複排除の設計

Lambda で DynamoDB に「チェック名 + イベントの `detail.uuid`（チェック項目の識別子）+ ステータス」を TTL 付き（例：30 日）で記録し、**初見の組み合わせだけ通知する**。これで同一リソースの再リフレッシュ・at-least-once の重複・短周期のフラッピングをまとめて吸収できる。TTL を過ぎても残っている指摘は再通知されるが、それは「30 日放置された ERROR」なので再通知が正しい。

### ダイジェストレーンの役割は 2 つ

1. **集約**：Trusted Advisor API（`ListRecommendations` / `ListRecommendationResources`）で全体を取得し、前回スナップショットとの差分から「新規 / 解消 / 継続」を 1 通にまとめる
2. **リコンシリエーション**：イベント配信はベストエフォートなので、プッシュで取りこぼした変化もここで必ず拾われる。即時レーンの見逃しに対する安全網

なお EventBridge のリファレンスには Trusted Advisor のダイジェスト系 detail-type（`Trusted Advisor Pursuit Weekly Digest` / `Daily Digest`）も追加されている。内容のカスタマイズや差分計算はできないが、要件が緩ければ自前 Lambda の代わりにまず試す価値はある。

### まず小さく始めるなら

いきなり 2 レーン作る必要はない。**最初の 1 歩は即時レーンだけ・チェック名 2〜3 個**でいい。SNS + Amazon Q Developer in chat applications（旧 AWS Chatbot）に直結すればコードゼロで動く（整形と重複排除は諦める）。ダイジェストが欲しくなった時点で Lambda を足す。逆に「まず全部流して様子を見る」は、チャンネルの信頼を初日に使い切るのでやらない。

## 前提条件とハマりどころ

- **Business / Enterprise On-Ramp / Enterprise のサポートプランが必要**。Basic / Developer ではチェック自体がほぼ動かない
- **EventBridge ルールと SNS トピックは必ず us-east-1 に作る**。Trusted Advisor はグローバルサービスで、イベントは us-east-1 にしか流れない。ap-northeast-1 にルールを作って「何も来ない」で数時間溶かすのが定番のハマり方
- **チェックの自動リフレッシュは週次程度**。「発生した瞬間」ではなく「リフレッシュで検出された瞬間」の通知。間隔を詰めたければ `RefreshTrustedAdvisorCheck` API の定期実行（最短 5 分間隔）で短縮できるが、リアルタイム検知が本当の要件なら AWS Config ルールや GuardDuty の領分。Trusted Advisor 通知は「定期健診の結果を、見に行かなくても届くようにする」ものと位置づける
- SNS トピックを KMS 暗号化している場合、キーポリシーで EventBridge からの発行を許可する（これも無通知でハマる）

## 提案するときの言い方

> Trusted Advisor は AWS が自動でやってくれる設定診断だが、結果は誰かが見に行かないと気づけない。これを「即座に対応が必要なものだけ即時に、それ以外は週 1 のサマリで」Slack に届くようにする。全部流すのではなく通知量を設計するので、アラート疲れで形骸化しない。追加コストは Lambda と DynamoDB でほぼゼロ（サポートプランは既存契約の範囲）。

## 参考

- [Monitoring AWS Trusted Advisor check results with Amazon EventBridge - AWS Support](https://docs.aws.amazon.com/awssupport/latest/user/cloudwatch-events-ta.html)
- [AWS Trusted Advisor events - Amazon EventBridge](https://docs.aws.amazon.com/eventbridge/latest/ref/events-ref-trustedadvisor.html)
- [AWS Trusted Advisor - AWS Support](https://docs.aws.amazon.com/awssupport/latest/user/trusted-advisor.html)
- [Trusted Advisor API Reference（ListRecommendations 等）](https://docs.aws.amazon.com/trustedadvisor/latest/APIReference/Welcome.html)
- [RefreshTrustedAdvisorCheck - AWS Support API Reference](https://docs.aws.amazon.com/awssupport/latest/APIReference/API_RefreshTrustedAdvisorCheck.html)
- [Tutorial: Get started with Slack - Amazon Q Developer in chat applications](https://docs.aws.amazon.com/chatbot/latest/adminguide/slack-setup.html)
- [aws/Trusted-Advisor-Tools（ExposedAccessKeys のイベント例）- GitHub](https://github.com/aws/Trusted-Advisor-Tools/blob/master/ExposedAccessKeys/README.md)
- [aws-samples/aws-trusted-advisor-scheduled-refresh - GitHub](https://github.com/aws-samples/aws-trusted-advisor-scheduled-refresh)
