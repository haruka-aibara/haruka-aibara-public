# Config 非準拠を定期リマインドで解消する運用

コンフォーマンスパックやマネージドルールをまとめて有効化すると、Config ルールは簡単に数十〜数百個になる。有効化した直後は非準拠一覧を眺めて頑張って直すが、コンソールは見に行かないと見えない。数週間もすると誰も見なくなり、非準拠が溜まったまま「検知はしているのに直らない」状態になる——ルールを大量に入れた組織のほとんどがここで止まる。

検知の仕組み（Config）はあるのに解消が進まない原因は、**「残っている非準拠」を定期的に目の前に持ってくる仕組みがない**こと。これを EventBridge + 定期リマインドで作る。

---

## 全体像：即時通知と定期リマインドは役割が違う

| 仕組み | 役割 | 限界 |
|---|---|---|
| 即時通知（EventBridge） | 新しく非準拠になった瞬間に気づく | Slack を流れて終わる。溜まった非準拠には無力 |
| 定期リマインド（週次サマリ） | 残っている非準拠を棚卸しし、解消を進めるエンジン | 即時性はない |

即時通知だけ入れて満足しがちだが、溜まった非準拠を減らすのは定期リマインドのほう。両方入れて役割を分ける。

---

## 即時通知：悪化に気づく

EventBridge で Config のコンプライアンス変化イベントを拾い、Slack（Amazon Q Developer in chat applications、旧 AWS Chatbot）に流す。

```json
{
  "source": ["aws.config"],
  "detail-type": ["Config Rules Compliance Change"],
  "detail": {
    "newEvaluationResult": {
      "complianceType": ["NON_COMPLIANT"]
    }
  }
}
```

ポイントは `NON_COMPLIANT` への変化だけ通知すること。準拠に戻った通知まで流すとノイズになり、チャンネルごとミュートされて終わる。

---

## 定期リマインド：残っている非準拠を週次で棚卸しする

EventBridge Scheduler で週 1 回 Lambda を起動し、非準拠のサマリを Slack に投稿する。取得はこの 1 コマンドで足りる。

```bash
# ルール単位の非準拠リソース数を取得
aws configservice describe-compliance-by-config-rule \
  --compliance-types NON_COMPLIANT \
  --query 'ComplianceByConfigRules[*].[ConfigRuleName, Compliance.ComplianceContributorCount.CappedCount]' \
  --output table
```

### サマリの作り方が続くかどうかを決める

数百件のリソース一覧をそのまま貼ると誰も読まない。リマインドとして機能する形はこう：

- **ルール単位の件数だけ**にする（リソース個別の一覧は貼らない。詳細はコンソールへのリンク）
- **前週比を添える**（+3 / -5 のように増減を見せる。減っていることが見えるとチームが続けられる）
- **悪化したルールだけハイライト**する（全部同列に並べると読み飛ばされる）

```
📋 Config 非準拠サマリ（前週比）
🔺 restricted-ssh: 4 件 (+2) ← 悪化
   encrypted-volumes: 12 件 (-3)
   access-keys-rotated: 7 件 (±0)
合計 23 件（前週 26 件）
```

前週比を出すには前回の件数をどこかに残す必要がある。DynamoDB や S3 に前回結果の JSON を 1 個置くだけで十分で、凝った作りにしない。

---

## リマインドの受け皿：非準拠は必ず 3 択に倒す

リマインドを流すだけでは減らない。通知された非準拠を「直す・自動修復に回す・例外化する」のどれかに必ず倒すルールをチームで決める。「あとで見る」を許すと元の状態に戻る。

### 1. 直す

普通の対応。担当を決めて修正する。リマインドに担当者やチームをメンションで載せられると流れやすい。

### 2. 自動修復に回す

毎回同じ手作業で直しているものは、Config の修復アクション（SSM Automation）に回してリマインド対象から消す。S3 のパブリックアクセスブロック再有効化などの定番はマネージドの Automation ドキュメントがある。

### 3. 例外化する

レガシーシステムでどうしても直せない、代替コントロールがある——そういうリソースはルールのスコープから外す。マネージドルールならタグや リソース ID でスコープを絞れるものが多い。

例外化で守るべきことは 2 つ：

- **ルールごと無効化しない**。1 リソースのためにルールを消すと、以降の新規違反も見えなくなる
- **理由を記録する**（なぜ除外したか、いつ見直すか）。記録がない例外は増える一方で、気づくと「スコアはいいのに実態はボロボロ」になる

---

## 減らす順序：まず「増やさない」、次に「減らす」

溜まった非準拠を前に全部直そうとすると挫折する。順序はこう：

1. **新規の非準拠をゼロに保つ**（即時通知に反応して、その日のうちに 3 択に倒す）
2. **既存の非準拠を重大度順に減らす**（S3 パブリック・SSH 全開放など漏洩に直結するものから。優先順位の付け方は FSBP の記事と同じ考え方）

「増やさない」が守れていれば、既存分は週次リマインドのペースで着実に減らせる。逆に新規流入を止めないまま既存を直しても、翌週には元の件数に戻る。

---

## ビジネス側への言語化

| 技術的な言い方 | ビジネス側に刺さる言い方 |
|---|---|
| Config ルールの非準拠を週次で通知する | セキュリティ設定の不備を「見つけたのに放置」で終わらせず、毎週減っていることを数字で示せる |
| 自動修復を設定する | 同じ設定ミスの手直しに毎回人が張り付く運用をなくせる |

「ルールを何百個入れた」は成果ではない。「非準拠が毎週減っている」が成果で、定期リマインドはそれを作るための仕組み。

---

## 参考

- [AWS Config ルールのコンプライアンス変化を EventBridge でモニタリングする](https://docs.aws.amazon.com/config/latest/developerguide/monitor-config-with-cloudwatchevents.html)
- [describe-compliance-by-config-rule（AWS CLI）](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/configservice/describe-compliance-by-config-rule.html)
- [AWS Config ルールによる非準拠リソースの修復（Remediation）](https://docs.aws.amazon.com/config/latest/developerguide/remediation.html)
- [コンフォーマンスパック](https://docs.aws.amazon.com/config/latest/developerguide/conformance-packs.html)
- [Amazon Q Developer in chat applications（旧 AWS Chatbot）](https://docs.aws.amazon.com/chatbot/latest/adminguide/what-is.html)
