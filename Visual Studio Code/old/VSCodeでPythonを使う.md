***

### VScode 拡張機能をインストール

1. **Python拡張機能**
   - Pythonコードの基本的な開発支援機能
   - コード補完、デバッグ、構文ハイライト等の基本機能を提供
   - Python開発には必須の拡張機能
   - https://marketplace.visualstudio.com/items?itemName=ms-python.python

2. **Ruff**
   - 高速なPythonのリンター（コード分析ツール）
   - コーディングスタイルやバグの可能性をチェック
   - コードの品質維持を支援
   - https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff

3. **Mypy Type Checker**
   - Pythonの型ヒントをチェックする機能
   - 型関連のバグを事前に発見
   - コードの信頼性向上に役立つ
   - https://marketplace.visualstudio.com/items/?itemName=ms-python.mypy-type-checker

4. **Pylint**
   - より包括的なPythonコード解析ツール
   - コーディング規約違反やエラーを詳細に検出
   - カスタマイズ性が高く、チーム開発に最適
   - https://marketplace.visualstudio.com/items/?itemName=ms-python.pylint

5. **autoDocstring - Python Docstring Generator**
   - Pythonの関数やクラスのドキュメント文字列を自動生成
   - 複数のドキュメント形式（Google、NumPy、Sphinxなど）をサポート
   - コード文書化の効率を大幅に向上
   - https://marketplace.visualstudio.com/items/?itemName=njpwerner.autodocstring

***

### Settings.json

1. Ruff 用

https://qiita.com/LaserBit/items/8dfd410ef65c19053ce2

```json
    "[python]": {
        "editor.codeActionsOnSave": {
            "source.fixAll": "explicit",
            "source.organizeImports": "explicit"
        },
        "editor.defaultFormatter": "charliermarsh.ruff"
    },
    "ruff.lineLength": 120,
    "ruff.lint.ignore": [
        "F401"
    ],
    "ruff.lint.preview": true,
    "ruff.lint.select": [
        "C",
        "E",
        "F",
        "W",
        "I"
    ],
    "ruff.logFile": "~/logs/ruff.log",
    "ruff.logLevel": "debug",
    "ruff.nativeServer": "on",
```

2. Pylance
pylance を動作させるため、`python.analysis.typeCheckingMode` で検索し、`off` -> `strict` に変更 

***

### WSL2 (ubuntu) 設定

1. uv 設定

https://docs.astral.sh/uv/getting-started/installation/

https://qiita.com/LaserBit/items/8dfd410ef65c19053ce2

```bash
# uv インストール
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env
```

2. ツール等
```bash
# pip
sudo apt install python3-pip

# pipx
sudo apt install pipx

# コードスタイル
uv tool install pycodestyle
uv tool install flake8
uv tool install pylint

# 静的型付け
# 使い方は以下のようなコマンドでプロジェクトのディレクトリ単位でチェック
# uvx --from pyre-check pyre --source-directory "project_dir" check
uv tool install pyre-check

# テスト
# 使い方
# uvx pytest test_xxx.py -v
uv tool install pytest
```

***

以下は任意

## Linux 版 Anaconda インストール

https://www.anaconda.com/download/success から最新の 64-bit Installer

参考：https://www.salesanalytics.co.jp/datascience/datascience141/#LinuxAnaconda

2025-03-30 時点の最新

```bash
wget https://repo.anaconda.com/archive/Anaconda3-2024.10-1-Linux-x86_64.sh

bash Anaconda3-2024.10-1-Linux-x86_64.sh

source .bashrc

conda config --set auto_activate_base false

eval "$(/home/haruka_aibara/anaconda3/bin/conda shell.bash hook)" 

conda install anaconda-navigator
```

### 必要なライブラリのインストール（apt-get）
```bash
sudo apt-get update
sudo apt-get install \
    libpci3 \
    libgl1-mesa-glx \
    libegl1-mesa \
    libxrandr2 \
    libxss1 \
    libxcursor1 \
    libxcomposite1 \
    libasound2 \
    libxi6 \
    libxtst6 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libx11-xcb-dev \
    libglu1-mesa-dev \
    libxkbcommon-dev \
    libxkbcommon-x11-dev \
    libxcb-xinerama0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-xkb1 \
    '^libxcb.*-dev'
```

### Conda関連のインストール
```bash
conda install -c anaconda qt qtpy
conda install -c conda-forge qt
```

### デバッグ用の環境変数設定（必要な場合のみ）
```bash
export QT_DEBUG_PLUGINS=1
```

これで、VSCode のターミナルで「anaconda-navigator」と入力すると
anaconda-navigator が起動します。

### その他
Numba
Pydantic
