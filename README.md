# China News Checker

独立项目，与桌面上的 `cursor` / `top-story-checker` 无关。

抓取 **CNN**、**The New York Times**、**The Guardian** 的 Google News 头条，手机友好界面，可部署到 Render。

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
3. 使用 `render.yaml` 或启动命令：`gunicorn -w 2 -b 0.0.0.0:$PORT app:app`
