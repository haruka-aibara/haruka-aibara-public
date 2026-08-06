# Trusted Advisor のアラートを Slack に通知するアーキテクチャ

## こういう場面で困る

Trusted Advisor は「コンソールを開いた人しか気づかない」サービス。公開設定になった S3 バケットや 0.0.0.0/0 に開いたセキュリティグループをチェックが検出して WARN / ERROR になっていても、誰かが見に行くまで放置される。月イチの棚卸しで開いて「これいつから赤かったんだ」となるのが典型的な失敗パターン。

これを解決するには、チェック結果が変化した時点で Slack に流れてくる仕組みを作ればいい。人がダッシュボードを見に行く運用は続かない。通知が来る運用に変える。

## 結論のアーキテクチャ

```
Trusted Advisor
  → EventBridge（us-east-1）
    → SNS トピック
      → Amazon Q Developer in chat applications（旧 AWS Chatbot）
        → Slack チャンネル
```

Lambda もカスタムコードも不要。全部マネージドサービスの設定だけで完結する。Slack への投稿は旧 AWS Chatbot（2025 年に Amazon Q Developer in chat applications に改称）に任せるのが最短で、Incoming Webhook の URL 管理や投稿用コードの保守から解放される。

### 前提条件

- **Business / Enterprise On-Ramp / Enterprise のサポートプランが必要**。Basic / Developer プランでは Trusted Advisor のチェックがほぼ動かないので、この仕組み自体が成立しない
- EventBridge ルールは **必ず us-east-1（バージニア北部）に作る**。Trusted Advisor はグローバルサービスで、イベントは us-east-1 にしか流れない。普段 ap-northeast-1 で作業していると、ルールを作ったのに何も飛んでこない、で数時間溶かす

### EventBridge のイベントパターン

WARN と ERROR だけ拾う。OK への回復まで流すとノイズになってチャンネルがミュートされる。

```json
{
  "source": ["aws.trustedadvisor"],
  "detail-type": ["Trusted Advisor Check Item Refresh Notification"],
  "detail": {
    "status": ["WARN", "ERROR"]
  }
}
```

セキュリティ系チェックだけに絞りたい場合は `detail.check-name` で対象チェック名を列挙する（例：`Security Groups - Specific Ports Unrestricted`、`Amazon S3 Bucket Permissions`）。全カテゴリを流すとコスト最適化系の通知に埋もれるので、チャンネルを分けるか絞るかは最初に決めておく。

ターゲットの SNS トピックも us-east-1 に作り、Amazon Q Developer in chat applications のコンソールで Slack チャンネルとそのトピックを紐付ければ完成。SNS トピックを KMS で暗号化している場合は、キーポリシーで EventBridge からの発行を許可しておくこと（これも無通知でハマるポイント）。

## 「瞬間」の実態を正直に言うと

このアーキテクチャで通知が飛ぶのは「チェック項目がリフレッシュされて WARN / ERROR になった瞬間」であって、「設定ミスが発生した瞬間」ではない。押さえておくべき制約が 2 つある。

1. **チェックの自動リフレッシュは週次程度**。Business 以上のプランでもリアルタイム監視ではない。詰めたい場合は EventBridge Scheduler + Lambda で `RefreshTrustedAdvisorCheck` API を定期実行してリフレッシュ間隔を短縮できる（各チェックのリフレッシュは最短 5 分間隔）。AWS 公式のサンプル実装もある
2. **イベント配信はベストエフォート**。EventBridge への配信は保証されない、と公式ドキュメントに明記されている

つまり「セキュリティグループが開いた瞬間に検知したい」が本当の要件なら、それは Trusted Advisor の仕事ではなく AWS Config ルールや GuardDuty の領分。Trusted Advisor 通知は「ベストプラクティス逸脱の定期健診結果を、見に行かなくても届くようにする」ものと位置づけるのが正しい。この住み分けを理解せずに Trusted Advisor をリアルタイム検知として提案すると、後で「検知が遅い」と言われて信頼を失う。

## 提案するときの言い方

技術的には上記の通りだが、ビジネス側にはこう伝わる：

> Trusted Advisor は AWS が自動でやってくれる設定診断だが、結果は誰かが見に行かないと気づけない。これを Slack に自動で流すことで、公開設定ミスやコスト無駄の指摘を「気づいた人が対応する」から「必ず目に入る」に変えられる。追加コストはほぼゼロ（サポートプランは既存契約の範囲）。

## 参考

- [Monitoring AWS Trusted Advisor check results with Amazon EventBridge - AWS Support](https://docs.aws.amazon.com/awssupport/latest/user/cloudwatch-events-ta.html)
- [AWS Trusted Advisor - AWS Support](https://docs.aws.amazon.com/awssupport/latest/user/trusted-advisor.html)
- [Tutorial: Get started with Slack - Amazon Q Developer in chat applications](https://docs.aws.amazon.com/chatbot/latest/adminguide/slack-setup.html)
- [Monitoring AWS services using Amazon Q Developer in chat applications](https://docs.aws.amazon.com/chatbot/latest/adminguide/related-services.html)
- [RefreshTrustedAdvisorCheck - AWS Support API Reference](https://docs.aws.amazon.com/awssupport/latest/APIReference/API_RefreshTrustedAdvisorCheck.html)
- [aws-samples/aws-trusted-advisor-scheduled-refresh - GitHub](https://github.com/aws-samples/aws-trusted-advisor-scheduled-refresh)
