# China News Checker

独立项目，与桌面上的 `cursor` / `top-story-checker` 无关。

从 **CNN**、**NYT**、**Guardian** 展示标题含 **China, Chinese, Taiwan, Taiwanese** 的新闻（每家多条，非头条）。

## 本地运行

双击 `start.bat` 或：

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
python app.py
```

打开 http://127.0.0.1:5000

## 部署（Render）

1. 将本文件夹推送到 GitHub 新仓库 `china-news-checker`
2. 在 [render.com](https://render.com) 用 GitHub 登录 → New Web Service → 选该仓库
3. 使用 `render.yaml` 或启动命令：`gunicorn -w 1 --threads 4 -b 0.0.0.0:$PORT --timeout 240 app:app`

## 每日自动更新（GMT 22:00 前）

Render 免费实例闲置会休眠并丢失 SQLite 数据，因此每日更新由 GitHub Actions
（`.github/workflows/daily-refresh.yml`）在 GMT 21:30 执行（21:45 自动重试），
把结果发布到 `daily-data` 分支的 `latest.json`；网站启动或打开首页时自动导入最新快照。
可在 GitHub → Actions → Daily news refresh → Run workflow 手动触发。
