# 把每日新闻日报发布到 GitHub Pages（保姆级教程）

目标：每天生成的日报自动推送到一个 GitHub 仓库，通过固定网址打开。

最终你会得到：`https://你的用户名.github.io/你的仓库名/`

> **顺序很重要**：先推送，再开 Pages。
> 空仓库没有任何分支，Pages 的 Branch 下拉里只会显示 `None`，开不了。

> **关于尖括号**：本文里 `https://github.com/你的用户名/daily-news.git` 这种是
> **示例格式**，要换成你自己的真实地址。**不要照抄尖括号 `< >`**——
> 在 PowerShell 里 `<` 和 `>` 是保留的重定向符号，会直接报
> 「"<"运算符是为将来使用而保留的」。命令里的地址一律用**英文双引号**包起来。

---

## 第 0 步：先确认两件事

1. 有一个 GitHub 账号（没有就去 github.com 注册，免费）。
2. 电脑上装了 Git：

```powershell
git --version
```

没装的话：`winget install --id Git.Git -e`

> **重要**：免费版 GitHub Pages 只支持**公开仓库**。日报内容是聚合的标题+链接+短摘要，
> 公开前请确认你接受"任何人都能看到"。

---

## 第 1 步：建仓库

1. 打开 https://github.com/new
2. **Repository name** 填 `daily-news`（随便起，记住它）
3. 选 **Public**（必须公开，否则 Pages 用不了）
4. **不要**勾选 "Add a README file" / .gitignore / license
   （我们本地已经有内容了，勾了反而会造成推送冲突）
5. 点 **Create repository**

建完页面会显示仓库地址，形如 `https://github.com/你的用户名/daily-news.git`，**记下来**。

此时仓库是**空的**——没有文件、没有提交、**没有分支**。这是正常的，下一步解决。

---

## 第 2 步：配置推送凭据（三选一）

### 方案 A：gh CLI（推荐，最省事）

```powershell
winget install --id GitHub.cli -e
gh auth login
```

`gh auth login` 的选项一路这样选：

- What account? → `GitHub.com`
- Protocol? → `HTTPS`
- Authenticate Git with your GitHub credentials? → `Yes`
- How to authenticate? → `Login with a web browser`

浏览器里输入它给的 8 位码，授权即可。**之后所有 git push 都不用再输密码。**

验证：

```powershell
gh auth status
```

看到 `Logged in to github.com` 就成了。

### 方案 B：Personal Access Token（PAT）

1. 打开 https://github.com/settings/tokens?type=beta
2. **Generate new token**
3. Name 填 `daily-news-push`，Expiration 建议 90 天（到期要换）
4. **Repository access** 选 `Only select repositories` → 勾选 `daily-news`
5. **Permissions → Repository permissions → Contents** 设为 `Read and write`
6. 点 **Generate token**，**立刻复制**（离开页面就看不到了）

推送地址里带上 token：

```powershell
git remote set-url origin "https://你的token@github.com/你的用户名/daily-news.git"
```

> ⚠️ token 等同于密码。不要写进任何提交的文件里。

### 方案 C：SSH 密钥

```powershell
ssh-keygen -t ed25519 -C "your@email.com"
Get-Content ~/.ssh/id_ed25519.pub
```

复制输出的整行，粘到 https://github.com/settings/keys → **New SSH key** → 保存。
之后 remote 地址用 `git@github.com:你的用户名/daily-news.git`。

---

## 第 3 步：首次推送（**先做这步**）

```powershell
cd D:\File\Codex\每日新闻
python scripts/render_html.py --all        # 先生成 HTML

cd site
git init -b main
git remote add origin "https://github.com/你的用户名/daily-news.git"   # 换成你自己的地址
git add -A
git commit -m "init: 每日新闻日报"
git push -u origin main
```

推送成功后，`main` 分支才在 GitHub 上真正存在。**这时才轮到开 Pages。**

> 地址不确定的话，在仓库首页点绿色 **Code** 按钮 → **HTTPS** → 复制那一串。
> 加完之后用 `git remote -v` 确认没填错。

---

## 第 4 步：开启 Pages

1. 进入仓库 → 顶部 **Settings**
2. 左侧栏 → **Pages**
3. **Source** 选 `Deploy from a branch`
4. **Branch** 这时应该能选到 `main` 了，目录选 `/ (root)`，点 **Save**
5. 顶部会显示：`Your site is live at https://你的用户名.github.io/daily-news/`

> **如果 Branch 下拉里还是只有 `None`**：说明第 3 步的推送没成功。
> 回仓库首页看一眼——**文件列表是空的就说明没推上去**。
> 常见原因是凭据没配好（跑 `gh auth status` 检查），或推送时报了错但被忽略。
> 别在这一步反复点，先把推送解决掉。

---

## 第 5 步：验证

1. 等 1–2 分钟（Pages 首次部署要编译）
2. 打开 `https://你的用户名.github.io/daily-news/`

看到日报列表 = 成功。打开某一天的页面能正常显示 = 完全成功。

**打不开怎么办**，按顺序排查：

- 仓库文件列表里到底有没有 `index.html`？
- Settings → Pages 有没有绿色提示 "Your site is live at..."？
- 刚推送完要等 1–2 分钟，别立刻下结论
- 仓库 → **Actions** 标签页，看部署有没有报错

---

## 第 6 步：日常自动发布

配好 Codex automation 后，每天 8:00 自动跑完整流程并推送。手动补一次的话：

```powershell
cd D:\File\Codex\每日新闻
python scripts/run_daily.py                 # 抓取 + 选稿（会停在待判栏目）
python scripts/classify.py --apply-index data/sections.json
python scripts/digest.py --editorial out/主编专栏.md
python scripts/render_html.py --all
cd site
git add -A
git commit -m "daily: 2026-10-08"
git push
```

建议放一个空的 `.nojekyll` 文件到 `site/`，避免 GitHub 的 Jekyll 处理下划线开头的文件：

```powershell
New-Item -Path site\.nojekyll -ItemType File -Force
```

---

## 授权边界（长期授权这个仓库 = 授权到什么程度）

已确认的授权范围：

- ✅ **推送到这一个仓库，之后不再每次询问**
- ✅ 每天自动提交、自动推送
- ❌ 不包含：换仓库、改仓库公开性、改 Pages 设置
- ❌ 不包含：推送到别的仓库、创建 Issue/PR、回复评论
- ❌ 不包含：把日报改成别的内容公开发布

超出以上范围的对外动作，仍然会先问。

---

## 常见问题

**Q：Pages 的 Branch 下拉里只有 `None`，选不到 `main`？**
仓库还是空的（没有提交）→ 先做完第 3 步推送。这是最常见的卡点。

**Q：直接跳过推送，在 GitHub 网页上新建一个 README 行不行？**
行——那样会创建 `main` 分支，Pages 就能选了。但**不推荐**：网页上有文件之后，
本地首次 `git push` 会因为历史不一致被拒绝，还得先 `git pull --rebase`。

**Q：push 报 `Authentication failed`？**
凭据没配好。跑 `gh auth status`；或用方案 B 的 token 地址重新 `git remote set-url`。

**Q：push 报 `rejected - fetch first`？**
远端有你本地没有的提交（比如你在网页上改过东西）。先 `git pull --rebase origin main` 再推。

**Q：仓库地址填错了，想改？**
`git remote set-url origin "正确的地址"`，然后 `git remote -v` 确认。

**Q：报「"<"运算符是为将来使用而保留的」？**
你把教程里的占位符 `<...>` 照抄进 PowerShell 了。`<` `>` 在 PowerShell 里是保留符号。
把整个地址换成真实的、并用英文双引号包起来，例如
`git remote add origin "https://github.com/zhangsan/daily-news.git"`。

**Q：日报里有境外媒体标题，公开会不会有版权问题？**
只存**标题 + 链接 + 短摘要**、不转载全文，属于常规聚合引用。建议在仓库根放一句声明
（"本页为新闻标题聚合，版权归原媒体所有"）。
