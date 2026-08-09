# syslog とは何か

障害が起きるたびに 10 台のサーバーへ順番に SSH して `journalctl` を叩いている。しかも「落ちたホスト」のログは、そのホストが落ちているせいで読めない。侵害調査の場面ではもっと悪くて、攻撃者が root を取っていればローカルのログは消されている可能性があり、残っていても信用できない。

**ログを生成したホストの外に、生成と同時に送り出す。** これが syslog の役割で、40 年前から変わっていない。

## syslog は 3 つの意味で使われる

会話が噛み合わなくなる原因がここにある。文脈によって指すものが違う。

| 呼び方 | 実体 |
|---|---|
| プロトコルとしての syslog | ネットワーク越しにログを送る形式（RFC 3164 / RFC 5424） |
| デーモンとしての syslog | ログを受け取って振り分ける常駐プロセス。実装が rsyslog / syslog-ng |
| API としての syslog | アプリが `syslog(3)` や `logger` でログを投げる口 |

「syslog を入れる」と言われたら、たいていは 2 番目（rsyslog か syslog-ng のインストール）を指している。

## ファシリティと重要度

syslog のメッセージには必ず**ファシリティ（どこから来たか）**と**重要度（どれくらいマズいか）**が付く。振り分けとフィルタはこの 2 つで行うので、ここだけは覚える必要がある。

重要度は 8 段階：

| 値 | 名前 | 意味 |
|---|---|---|
| 0 | emerg | システムが使用不能 |
| 1 | alert | 即時対応が必要 |
| 2 | crit | 致命的 |
| 3 | err | エラー |
| 4 | warning | 警告 |
| 5 | notice | 正常だが注目に値する |
| 6 | info | 情報 |
| 7 | debug | デバッグ |

ファシリティは `kern`(0), `user`(1), `mail`(2), `daemon`(3), `auth`(4), `syslog`(5), `lpr`(6), `news`(7), `uucp`(8), `cron`(9), `authpriv`(10), `ftp`(11) と、**自由に使える `local0`〜`local7`**(16〜23)。

自社アプリのログを syslog に流すときは `local0`〜`local7` のどれかを割り当てるのが慣習。ファシリティで分けておくと、集約サーバー側で「local3 は決済アプリだから別ファイル・別保存期間」といった振り分けが設定 1 行で書ける。

送信されるヘッダの先頭にある `<134>` のような数字（PRI）は `ファシリティ × 8 + 重要度` で、134 なら `local0.info`。パケットキャプチャでログの中身を読むときにこの計算を知っていると早い。

## 手元から試す：logger

設定を書く前に、まず 1 行流して疎通を確認するのが定石。

```bash
logger -p local0.info "test message"          # local0.info で 1 行送る
logger -p auth.err -t myapp "auth failed"     # タグ（プログラム名）を付ける
echo "from stdin" | logger -p local3.notice
```

`journalctl -f` や `tail -f /var/log/messages` を別ターミナルで開きながら叩けば、どの経路でどこに落ちるかが一目で分かる。フィルタ設定を書いたあとの検証も、これで足りる。

## RFC 3164 と RFC 5424 の違い

**RFC 3164（BSD syslog）** は 2001 年に「現状こう動いている」を追認しただけの情報提供 RFC。タイムスタンプに年もタイムゾーンもミリ秒もない（`Oct  8 13:22:01`）。

```
<134>Oct  8 13:22:01 web01 nginx: connection refused
```

**RFC 5424** は 2009 年の標準仕様。RFC 3339 形式のタイムスタンプ（年・タイムゾーン・秒未満あり）、構造化データ（`[key="value"]`）、UTF-8 が入った。

```
<134>1 2026-08-09T13:22:01.123456+09:00 web01 nginx 1234 ID47 [origin ip="10.0.1.5"] connection refused
```

**現場での落とし穴はタイムスタンプ**。RFC 3164 のままだと年もタイムゾーンも落ちるので、年をまたぐ調査や複数リージョンのログ突き合わせで簡単に破綻する。集約するなら送信側・受信側とも RFC 5424 を使う。実装側の設定名では、rsyslog なら `RSYSLOG_SyslogProtocol23Format` テンプレート、syslog-ng なら `syslog()` ドライバがこれに当たる。

なお、**どの RFC でもホスト名は送信側が名乗るだけの自己申告**で、検証されない。信用できるのは受信側が見た接続元 IP（rsyslog の `$fromhost-ip`）のほう。調査ではこちらを軸にする。

## 転送方式：UDP 514 を選ばない

| 方式 | ポート | 実態 |
|---|---|---|
| UDP | 514 | 昔からのデフォルト。到達保証なし。混雑時に**黙って落ちる** |
| TCP | 514 | 到達性は上がるが、TCP レイヤの ACK であってアプリが処理した保証ではない |
| TLS | 6514 | 暗号化＋相互認証（RFC 5425） |
| RELP | 2514 など | rsyslog 独自。アプリケーションレベルの ACK があり最も欠損しにくい |

UDP は「ログが消えたことすら分からない」のが致命的で、監査目的のログには使えない。**集約するなら TLS（6514）が既定**と考えてよい。設定は [ログ集約サーバーの構築](ログ集約サーバーの構築.md) で扱う。

## journald があるのに、なぜ syslog を使うのか

systemd の journald はローカルのログを一元管理してくれるが、以下は syslog デーモンの領分として残る。

- **他ホストへの転送**（`systemd-journal-remote` もあるが採用例は少なく、対応機器も限られる）
- **ネットワーク機器・アプライアンスからの受信**。ルーター、スイッチ、ファイアウォール、ストレージは syslog しか喋らない
- **柔軟な振り分けと加工**（ファシリティ別・ホスト別のファイル出力、フィルタ、外部システムへの中継）

そのため実運用では **journald と rsyslog が両方動いている**構成が普通で、journald が受けたログを rsyslog が読み出して転送する。この連携は 2 通りある。

```ini
# /etc/systemd/journald.conf — journald 側から syslog ソケットへ流す
[Journal]
ForwardToSyslog=yes
```

```
# /etc/rsyslog.conf — rsyslog 側からジャーナルを読む（推奨）
module(load="imjournal" StateFile="imjournal.state")
```

`imjournal` のほうが構造化されたメタデータを保てるので、新しく組むならこちら。

### ハマりどころ 1：レートリミットで黙って捨てられる

journald にも rsyslog の `imjournal` にもレートリミットがあり、大量出力時にメッセージが**破棄される**。ログに `Suppressed N messages due to rate-limiting` と出ていたら、その区間のログは存在しない。障害時に限ってログが飛ぶという最悪の挙動なので、集約対象のホストでは緩めるか無効化する。

```ini
# /etc/systemd/journald.conf
RateLimitIntervalSec=0
RateLimitBurst=0
```

### ハマりどころ 2：Amazon Linux 2023 に rsyslog がない

AL2023 は既定で rsyslog を入れておらず、`/var/log/messages` も存在しない。ログは journald だけにある。AL2 の感覚で `tail /var/log/messages` を叩いて「ログが出ていない」と誤解しやすい。必要なら明示的に入れる。

```bash
sudo dnf install -y rsyslog
sudo systemctl enable --now rsyslog
```

## ローテーションは syslog の仕事ではない

rsyslog も syslog-ng もファイルを書き続けるだけで、サイズ管理は logrotate が担当する。ローテーション後に**デーモンへ通知しないと、消えたファイルのディスクリプタを掴んだまま書き続けてディスクだけ減る**という典型的な事故になる。

```
/var/log/remote/*/*.log {
    daily
    rotate 30
    compress
    missingok
    postrotate
        /usr/bin/systemctl kill -s HUP rsyslog.service
    endscript
}
```

## 参考

- [RFC 5424 — The Syslog Protocol](https://datatracker.ietf.org/doc/html/rfc5424)
- [RFC 3164 — The BSD syslog Protocol](https://datatracker.ietf.org/doc/html/rfc3164)
- [RFC 5425 — TLS Transport Mapping for Syslog](https://datatracker.ietf.org/doc/html/rfc5425)
- [systemd-journald.service(8) — freedesktop.org](https://www.freedesktop.org/software/systemd/man/latest/systemd-journald.service.html)
- [logger(1) — man7.org](https://man7.org/linux/man-pages/man1/logger.1.html)
