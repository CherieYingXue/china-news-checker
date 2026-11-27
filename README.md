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

## 更新新闻

网站不会自动更新。打开首页点「获取新闻」即可获取所选媒体过去 24 小时内的新闻，
通常约 1 分钟，期间页面会自动刷新显示进度。Render 免费实例闲置后会休眠并清空数据，
再次打开时点一次「获取新闻」即可。
