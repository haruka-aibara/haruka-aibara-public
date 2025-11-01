---
title: "Playbookとは"
slug: "playbook"
---

# Playbookとは

## Playbookの概要

Playbookは、Ansibleの自動化の中核となる設定ファイルで、システム構成やアプリケーションデプロイを簡潔かつ再現性高く実行できます。

## Playbookの基本構造

Playbookは、YAML形式で記述された実行したいタスクの集まりです。複数のホストに対して順序立てて実行される一連の処理を定義します。

## YAMLの基礎知識

Playbookを作成するためには、YAML形式の理解が必要です。

- **リスト表記**: ハイフン(`-`)を使って各要素を指定します
- **ディクショナリ表記**: キーと値をコロン(`:`)で区切ります
- **インデント**: 半角スペース2つでレベルを表現します
- **コメント**: `#`記号で行コメントを記述できます
- **文字列**: 通常はクォートなしでも記述可能ですが、特殊文字を含む場合はクォート(`"`)で囲みます

## Playbook基本要素

### 1. 名前（name）

Playbookやタスクに付ける人間が理解しやすい説明文です。実行時のログに表示され、何をしているかが一目でわかるようになります。

```yaml
- name: Webサーバーのセットアップ
```

### 2. ホスト（hosts）

どのサーバーグループに対して実行するかを指定します。インベントリファイルで定義したグループ名を指定します。

```yaml
hosts: webservers
```

### 3. タスク（tasks）

実際に実行する処理を定義します。各タスクはモジュールを使用して定義されます。

```yaml
tasks:
  - name: Nginxのインストール
    yum:
      name: nginx
      state: present
```

## Playbookの構成

Playbookは大きく分けて2つのセクションから構成されます：

1. **サマリ部**：Playbookの全体設定
   - 実行対象ホストの指定
   - 実行ユーザーの設定
   - 変数の定義

2. **タスク部**：実際の処理内容
   - 各タスクの定義
   - 使用するモジュールの指定
   - タスクのパラメータ設定

## Playbookの実践例

以下は、Nginxをインストールして起動する簡単なPlaybookの例です：

```yaml
# Webサーバーセットアップ用Playbook
- name: Nginxサーバーのセットアップ
  hosts: webservers
  become: true
  
  tasks:
    - name: Nginxパッケージのインストール
      yum:
        name: nginx
        state: present
      
    - name: Nginxサービスの起動と自動起動設定
      service:
        name: nginx
        state: started
        enabled: yes
```

## Playbookの利点

- **冪等性**: 何度実行しても同じ結果になる
- **再利用性**: 一度作成したPlaybookは他の環境でも利用可能
- **バージョン管理**: Gitなどでコード管理可能
- **ドキュメント化**: Playbookそのものが実行内容のドキュメントになる

## Playbookの実行方法

Playbookは以下のコマンドで実行します：

```bash
ansible-playbook playbook名.yaml
```

## まとめ

Playbookは、Ansibleの強力な自動化機能を活用するための鍵となるものです。YAML形式で記述され、サーバーのセットアップから複雑なアプリケーションデプロイまで、様々な自動化タスクを簡潔かつ再現性高く実行できます。初心者の方は、まず小さなPlaybookから始めて徐々に理解を深めていくことをお勧めします。

