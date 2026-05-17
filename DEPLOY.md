# 部署 China News Checker（手机公网访问）

## 第一步：创建 GitHub 仓库（约 1 分钟）

1. 打开 https://github.com/new  
2. Repository name 填 **`china-news-checker`**  
3. 选 **Public**，不要勾选 “Add a README”  
4. 创建仓库  

## 第二步：推送本机代码

在 `C:\Users\xhs\Desktop\china-news-checker` 打开终端：

```bash
git push -u origin main
```

若提示登录，用 GitHub Personal Access Token 作为密码。

## 第三步：Render 部署（约 5 分钟）

1. 打开 https://render.com ，用 GitHub 登录  
2. **New +** → **Web Service** → 选择 **`china-news-checker`** 仓库  
3. Name 可填 `china-news-checker`  
4. Build Command：`pip install -r requirements.txt`  
5. Start Command：`gunicorn -w 2 -b 0.0.0.0:$PORT app:app`  
6. 点 **Create Web Service**  

部署完成后公网地址一般为：

**https://china-news-checker.onrender.com**

（以 Render 面板显示的 URL 为准。）

## 手机使用

- 用浏览器打开上述链接  
- iOS/Android：浏览器菜单 → **添加到主屏幕**（PWA）

## 同一 WiFi 内测（无需部署）

电脑运行 `start.bat` 后，手机浏览器访问：

`http://电脑局域网IP:5000`

（例如 `http://192.168.1.41:5000`）
