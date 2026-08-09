# rsyslog と syslog-ng の選び方

ログ集約を組むことになり、調べると rsyslog と syslog-ng が並んで出てくる。機能一覧を見比べてもどちらも「TLS 対応・ディスクバッファ・フィルタ・多様な出力先」と書いてあって、決め手が分からない。

結論から言うと、**機能差で決まる場面はほとんどなく、既にディストリビューションに入っているほう（＝ほぼ rsyslog）を使えばよい**。それでも syslog-ng を選ぶ理由がある場面は限られていて、そこだけ知っておけば判断できる。

## まず既定を確認する

| ディストリビューション | 既定 |
|---|---|
| RHEL / Rocky / AlmaLinux | rsyslog |
| Ubuntu / Debian | rsyslog |
| Amazon Linux 2 | rsyslog |
| Amazon Linux 2023 | なし（journald のみ。rsyslog はリポジトリから導入） |
| SUSE Linux Enterprise | rsyslog |

**既定を捨てて別のデーモンを入れるのは、それ自体がコスト**になる。ディストリビューションが同梱するデフォルト設定・logrotate 設定・SELinux ポリシー・パッケージ更新の恩恵から外れ、キッティングとドキュメントを自前で持つことになる。この負担を上回る理由がない限り、rsyslog のままでいい。

## 設定ファイルの書き味の違い

実務で最も体感差が出るのはここ。同じ「ローカルログを集約サーバーへ TLS 転送する」を書き比べる。

**rsyslog（RainerScript）** — アクションにパラメータをぶら下げていく形：

```
*.* action(type="omfwd"
           target="logs.example.internal" port="6514" protocol="tcp"
           StreamDriver="gtls" StreamDriverMode="1" StreamDriverAuthMode="x509/name")
```

**syslog-ng** — source / destination / filter を定義し、`log{}` で線をつなぐ形：

```
destination d_central {
  syslog("logs.example.internal" transport("tls") port(6514)
    tls(ca-dir("/etc/syslog-ng/ca.d")
        key-file("/etc/syslog-ng/key.pem")
        cert-file("/etc/syslog-ng/cert.pem")));
};

log { source(s_local); destination(d_central); };
```

syslog-ng は部品に名前を付けてから配線するので、**経路が増えたときに構造が壊れにくい**。rsyslog は 1 経路なら短く書けるが、複数の宛先・条件分岐が増えると、レガシー記法（`*.info @@host:514`）と RainerScript が混在した読みづらい設定になりやすい。

一方 rsyslog は**Web に出回っている情報量が圧倒的に多い**。トラブル時に検索して答えが見つかる確率は無視できないメリットで、これが既定を推す実質的な理由でもある。

## 判断軸

| 観点 | rsyslog | syslog-ng |
|---|---|---|
| ディストリビューションの既定 | ほぼ全て | 明示的に導入が必要 |
| 設定の見通し（経路が多いとき） | 悪化しやすい | 構造を保ちやすい |
| 情報量・事例 | 多い | 少なめ |
| 非構造ログのパース | 正規表現ベースで自力 | `patterndb` / パーサ群が充実 |
| 到達保証 | RELP（アプリレベル ACK）が使える | ディスクバッファ `reliable(yes)` |
| 商用サポート | ディストリビューションのサポートに含まれる | 別途 syslog-ng PE（One Identity） |

**syslog-ng を積極的に選ぶ場面は 2 つに絞られる。**

1. **多数の異種ソースを正規化して SIEM に流す集約サーバー**。ネットワーク機器・アプライアンス・アプリのバラバラなログを構造化する必要がある場合、パーサ周りの作り込みやすさで差が出る
2. **すでに社内標準が syslog-ng**。この場合は揃えるほうが正しい

逆に、**各ホストのエージェントとして入れるなら rsyslog 一択**でよい。転送するだけの用途で機能差は出ず、既定であることの価値が勝つ。

## そもそも syslog デーモンを使うべきかを先に決める

比較の前に確認したいのは「そのログはどこへ行くのか」。行き先がクラウドのログ基盤なら、syslog デーモンを経由しない選択肢のほうが素直なことがある。

- **AWS の EC2 から CloudWatch Logs へ送る** → CloudWatch エージェント（`journald` を直接読める）で足り、rsyslog を挟む必要はない
- **Kubernetes / コンテナ** → 標準出力を Fluent Bit などが拾う設計が既定。syslog は出番がない
- **Loki / Elasticsearch へ送る** → Promtail や Fluent Bit といった専用エージェントのほうが構造化とラベル付けで有利（[Loki でのログ管理](../Prometheus%20and%20Grafana/Lokiでのログ管理.md)）

**syslog デーモンが要るのは主に次の場合**：

- **syslog しか喋れない機器がある**。ルーター、スイッチ、ファイアウォール、ストレージ、UPS などのアプライアンスは今も syslog 送信が唯一の出口
- **オンプレの Linux サーバー群を、まず 1 か所に集めたい**
- **クラウドのログ基盤に出す前段で、ホスト側にバッファと振り分けを置きたい**

用途が決まっていないのに「とりあえずログ基盤」を先に建てても使われずに終わる。**誰が何の調査でそのログを引くのかが決まってから**構築する。

## 移行するときに引っかかる点

既存の rsyslog から syslog-ng へ（あるいは逆へ）移す場合、以下は設定の対応表が存在せず、都度作り直しになる。

- **フィルタ条件**。rsyslog の `if $programname == "nginx"` と syslog-ng の `filter { program("nginx"); }` は概念は同じでも記法が別物
- **テンプレート**。出力ファイル名の組み立て（`%HOSTNAME%` と `${HOST}`）で変数名が違う
- **キュー／バッファ**。rsyslog のディスク支援キューと syslog-ng の `disk-buffer()` はパラメータ体系が異なり、サイズ設計をやり直す必要がある

移行期間中は**両方を同時に走らせない**。同じ `/dev/log` ソケットを奪い合い、どちらが受けたか分からないログの取りこぼしが起きる。切り替えは停止→起動で行い、切り替え直後に `logger` で疎通を確認する。

## 参考

- [rsyslog documentation](https://www.rsyslog.com/doc/)
- [syslog-ng Open Source Edition documentation](https://syslog-ng.github.io/)
- [rsyslog — RainerScript](https://www.rsyslog.com/doc/rainerscript/index.html)
- [Amazon CloudWatch エージェントの設定 — AWS ドキュメント](https://docs.aws.amazon.com/ja_jp/AmazonCloudWatch/latest/monitoring/CloudWatch-Agent-Configuration-File-Details.html)
