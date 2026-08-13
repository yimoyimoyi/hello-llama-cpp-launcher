# Llama.cpp GUI ランチャー

**PySide6** ベースの [llama.cpp](https://github.com/ggerganov/llama.cpp) 用グラフィカルフロントエンド。Windows / Linux / WSL 対応。

- モデルパラメータのビジュアル設定
- llama.cpp バイナリダウンロード（aria2c 16 スレッド高速化）
- プロセス管理と外部コンソール
- ダーク / ライト デュアルテーマ
- 简体中文 / English / 日本語

---
## スクリーンショット
<img width="518" height="659" alt="image" src="https://github.com/user-attachments/assets/0e132d24-9b0c-423c-b6a7-f01ce65bfa2c" /><img width="518" height="659" alt="image" src="https://github.com/user-attachments/assets/b26ccd20-18c3-46ab-b5d5-da7ac86ff926" /><img width="518" height="659" alt="image" src="https://github.com/user-attachments/assets/ceaf52df-077c-4eb7-b5e8-355f6ccb2c12" />



## クイックスタート

### 必要条件

- **Python** 3.8+
- **PySide6** ≥ 6.5.0

### インストール

すべての依存関係は `requirements.txt` に宣言されており、標準 pip でインストールします。

#### Windows

| 方法 | 操作 | 説明 |
|------|------|------|
| pip | `setup_pip.bat` をダブルクリック | システム Python にインストール |
| uv | `setup_uv.bat` をダブルクリック | `.venv` 仮想環境に分離 |

または手動: `pip install -r requirements.txt`

#### Linux / macOS

```bash
chmod +x setup_pip.sh setup_uv.sh start.sh
```

| 方法 | 操作 | 説明 |
|------|------|------|
| pip | `bash setup_pip.sh` | システム Python にインストール |
| uv | `bash setup_uv.sh` | `.venv` 仮想環境に分離 |

または手動: `pip3 install -r requirements.txt`

### 起動

| プラットフォーム | 操作 |
|------------------|------|
| Windows | `start.bat` をダブルクリック |
| Linux/macOS | `bash start.sh` |

`start.bat` / `start.sh` は uv `.venv` > システム Python を自動検出し、すぐに使用できます。

---

## ユーザーガイド

### 基本設定

1. **⚙ 設定** タブを開く
2. **Bin ディレクトリ** を設定 — `llama-cli` / `llama-server` を含むパス
3. **モデルディレクトリ** を設定 — `.gguf` ファイルを含むパス
4. **📊 パラメータ** タブに切り替え
5. ドロップダウンからモデルを選択 → パラメータを調整 → **▶ 開始** をクリック

### バイナリのダウンロード

ローカルバイナリがない場合:

1. 設定で **📡 利用可能なファイルを取得** をクリック
2. プラットフォーム固有のリリースリストを待つ（初回は30分間キャッシュ）
3. ボタンリストから目的のバックエンドを見つけてクリックしてダウンロード
4. ダウンロード後、ファイルは自動的に Bin ディレクトリに展開され、検出が更新される

ダウンロードは GitHub Release API を使用し、aria2c (`--split=16 --min-split-size=1M`) マルチスレッド高速化を行います。

### Server モード

起動前に **Server (API) モード** をチェックすると、自動的にブラウザで `http://localhost:8080` を開きます。ポートはカスタマイズ可能です。

### モデルプリセット

各モデルはパラメータプリセットを個別に保存します。モデル切り替え時に自動的に読み込まれます。**💾 保存** をクリックして現在のパラメータを保存し、**🗑 削除** でクリアします。

### 推論モード

- **通常** — `--reasoning on` で思考を通常出力します。「思考 Token 制限」欄で思考予算を設定できます（`--reasoning-budget N`。対応モデル/バージョンで有効）
- **非表示** — `-rea off` で思考を無効化します（推論対応モデル（Qwen3 / DeepSeek 系など）でのみ有効。VibeThinker 等のテキスト式思考モデルはパラメータで無効化できません）

### 外部コンソール

有効にすると、ターミナルウィンドウで標準入力から対話できます。

---

## プロジェクト構成

```
├── main.py                      # メインエントリポイント
├── start.bat / start.sh         # 起動スクリプト
├── setup_pip.bat / setup_pip.sh # pip インストール
├── setup_uv.bat / setup_uv.sh   # uv インストール
│
├── src/
│   ├── config.py                # パス / QSS ローダー / i18n エンジン / デフォルト設定
│   ├── widgets.py               # カスタムウィジェット（折りたたみパネル / コンボボックス / コンソール）
│   ├── download.py              # ダウンロードスレッド + VRAM 検出スレッド
│   ├── backends.py              # バックエンドレジストリ（CUDA/Vulkan/SYCL/CPU）
│   ├── launcher.py              # プロセス起動スレッド
│   ├── platform.py              # プラットフォームディスパッチ（Win/Linux 自動インポート）
│   ├── platform_win.py          # Windows プラットフォーム関数
│   └── platform_linux.py        # Linux プラットフォーム関数
│
├── assets/
│   ├── qss/dark_style.qss       # ダークテーマスタイルシート
│   ├── qss/light_style.qss      # ライトテーマスタイルシート
│   ├── ui_config.json           # UI 表示要素の設定
│   └── README.md
│
└── locales/
    ├── zh.json                  # 簡体中国語
    ├── en.json                  # 英語
    └── ja.json                  # 日本語
```

実行時に自動生成（`.gitignore` 推奨）:

| ファイル | 説明 |
|----------|------|
| `launcher_config.json` | ウィンドウ位置、プリセット、言語、テーマなどの永続設定 |
| `assets/release_cache.json` | GitHub Release キャッシュ（30分間有効） |
| `bin/` | ダウンロードされた llama.cpp バイナリ |
| `.venv/` | uv 仮想環境 |

---

## カスタマイズ

### 外観の変更

`assets/qss/dark_style.qss` または `assets/qss/light_style.qss` を標準の Qt Style Sheet 構文で編集します。再起動で反映されます。

ダークテーマのカラーシステム:

| レベル | カラー | 用途 |
|--------|--------|------|
| ベース | `#1e1e2e` | ウィンドウ / タブ背景 |
| サーフェス | `#28283c` | 入力 / コンボボックス / ボタン |
| ホバー | `#323248` | マウスホバーハイライト |
| ボーダー | `#3a3a50` | 区切り線 / 入力ボーダー |
| アクセント | `#5a9cf0` | フォーカス / 選択 / リンク |

ライトテーマ対応: `#f2f3f5` → `#ffffff` → `#e8eaf0` → `#d4d6dc` / `#3d88e0`

### テキストの変更

| 必要事項 | ファイル |
|----------|----------|
| 多言語翻訳 | `locales/*.json` |

### 新しい言語の追加

`locales/` に `zh.json` と同じ構造の `.json` ファイルを配置します。ファイル名が言語コードになります。設定のドロップダウンに自動的に表示されます。

---

## バックエンドサポート

ダウンロード可能なバックエンド（プラットフォーム適応、`.zip` または `.tar.gz` のみ表示）:

| バックエンド | Windows | Linux |
|-------------|:-------:|:-----:|
| NVIDIA CUDA 12.4 / 13.1 | ✅ | ✅ |
| AMD HIP / ROCm | ✅ | ✅ |
| Vulkan (汎用) | ✅ | ✅ |
| Intel SYCL / OpenVINO | ✅ | ✅ |
| CPU (汎用) | ✅ | ✅ |
| ARM64 | ✅ | ✅ |
| macOS | — | ✅ |

---

## プラットフォーム注意事項

### Linux

- **aria2c** — 初回ダウンロード時に `sudo apt install aria2` / `sudo pacman -S aria2` を自動試行
- **スクリプトエクスポート** — `.sh` として保存し、自動 `chmod 755`
- **外部コンソール** — `subprocess.Popen` でシステムターミナルで起動
- **VRAM 検出** — `nvidia-smi` に依存

### macOS

- ダブルクリックで起動しない場合 → ターミナルで `python3 main.py` を実行
- ダウンロード機能は `.tar.gz` に対応
- aria2c は手動インストールが必要: `brew install aria2`

### WSL

- GUI には Windows 側の X Server（VcXsrv / GWSL）または WSLg が必要
- ダウンロード機能は正常に動作
- ファイルパスは Linux 形式を使用

---

## よくある質問

**Q: 起動時に「実行ファイルが見つかりません」エラーが発生？**  
A: 設定で Bin ディレクトリを設定するか、**📡 利用可能なファイルを取得** をクリックしてダウンロードしてください。

**Q: 問題を報告するには？**  
A: GitHub Issues 機能を適切にご利用ください。

**Q: 言語を切り替えるには？**  
A: 設定 → 🎨 外観 → 言語ドロップダウン、即時反映されます。

**Q: UI フォントが小さすぎる / 大きすぎる？**  
A: 設定 → 📐 スケール → スライダーをドラッグ（50%-200%）。適応モードはウィンドウサイズに応じて自動スケーリングします。

**Q: ダウンロード速度が遅い？**  
A: `src/config.py` の `MIRROR_BASE_URLS` を編集してミラーを追加するか、`PROXY_HOST` / `PROXY_PORT` を設定してください。プロキシの使用または手動ダウンロードを推奨します。

**Q: 現在のパラメータを後で使用するために保存するには？**  
A: パラメータタブで **💾 保存** をクリックします。パラメータはモデル名ごとに保存され、モデル切り替え時に自動復元されます。

---

## ライセンス

MIT License
