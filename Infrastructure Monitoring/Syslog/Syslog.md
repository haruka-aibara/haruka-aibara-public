# Syslog

複数ホストのログを 1 か所に集めるための仕組み。プロトコルとしての syslog と、その実装である rsyslog / syslog-ng を扱う。

## 記事一覧

- [syslog とは何か](syslogとは何か.md) — ファシリティ・重要度・RFC の違い、journald との関係
- [rsyslog と syslog-ng の選び方](rsyslogとsyslog-ngの選び方.md) — どちらを使うかの判断軸
- [ログ集約サーバーの構築](ログ集約サーバーの構築.md) — TLS 転送・欠損対策・セキュリティ上の設計
