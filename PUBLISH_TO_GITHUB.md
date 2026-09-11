# 如何把这个 MCP + Skill 分享到 GitHub

我已完成**发布前准备**，剩下的是需要你本人操作的部分（涉及你的账号授权）。

---

## 一、我替你做完的事

| 项目 | 状态 |
|---|---|
| 隐私/密钥审计 | ✅ **无泄露**。没有你的机器名、用户名、真实安装路径、API key 或 token |
| `.gitignore` | ✅ 已建。排除 `.venv/`、编译产物 `uia/bin|obj`、测试数据、DEM 瓦片、`*.terrain` |
| `LICENSE` | ✅ MIT + QuadSpinner 商标与授权免责声明 |
| 包结构 | ✅ 19 个文件，`pip install -e .` 可直接安装 |
| 离线自检 | ✅ 8 组全通过 |
| 文档诚实性 | ✅ 已把"未能完全验证"的部分明确标注（见 README 的验证状态表） |

审计中唯一的"命中"是 `config.py` 里的**安装路径探测提示**
（`D:\Progame Files\Gaea 2`、`C:\Program Files\QuadSpinner\Gaea 2`）。
这是必要的自动探测，不含任何个人信息，可以保留。

---

## 二、发布前你必须决定的两件事

### ① 提交身份（重要）

你当前的全局 git 配置是：

```
user.name  = chun.zhong
user.email = chun.zhong@lotuscars.com.cn      ← 公司邮箱
```

**公开仓库的每一个 commit 都会永久暴露这个邮箱。** 建议为这个仓库单独配置个人身份，
或用 GitHub 的 noreply 邮箱（在 GitHub ▸ Settings ▸ Emails 里可查到
`<ID>+<用户名>@users.noreply.github.com`）：

```powershell
cd F:\06_2026\9\910deepseek41\gaea_mcp
git config user.name  "你的GitHub用户名"
git config user.email "你的GitHub用户名@users.noreply.github.com"   # 或你的个人邮箱
```

这条只作用于本仓库，不影响你公司项目。

### ② 认证方式

本机当前**没有 GitHub 凭据**（只有公司 GitLab 与 Coding.net），也**没有 `gh` CLI**。
HTTPS 推送需要 Personal Access Token（GitHub 已不支持密码）。

---

## 三、具体步骤

### 准备：配置代理（本机必需）

你的网络需要走本地代理，Git 尚未配置：

```powershell
git config --global http.https://github.com.proxy http://127.0.0.1:7897
```

### 方案 A：GitHub CLI（最省事，推荐）

```powershell
winget install --id GitHub.cli          # 或 scoop install gh
gh auth login                            # 选 HTTPS → 浏览器授权
```

然后我可以替你执行：

```powershell
cd F:\06_2026\9\910deepseek41\gaea_mcp
git init -b main
git add .
git commit -m "feat: MCP server + skill for driving Gaea 2"
gh repo create gaea-mcp --public --source=. --remote=origin `
  --description "MCP server + AI skill that actually drives QuadSpinner Gaea 2: author .terrain, validate in Gaea, build and export" `
  --push
```

### 方案 B：手动建仓 + Token

1. 浏览器打开 https://github.com/new
   - Repository name: `gaea-mcp`
   - 选 **Public**，**不要**勾选 Add README / .gitignore / license（避免冲突）
2. 生成 Token：https://github.com/settings/tokens
   → Fine-grained token，权限给 **Contents: Read and write**
3. 推送（把 `<TOKEN>` 和 `<你的用户名>` 换掉）：

```powershell
cd F:\06_2026\9\910deepseek41\gaea_mcp
git init -b main
git add .
git commit -m "feat: MCP server + skill for driving Gaea 2"
git remote add origin https://<你的用户名>@github.com/<你的用户名>/gaea-mcp.git
git push -u origin main
# 提示密码时粘贴 <TOKEN>
```

> Token 会被 Windows 凭据管理器保存，**不要**把它写进任何文件或提交。

---

## 四、建议补的仓库设置

**Description**
```
MCP server + AI skill that actually drives QuadSpinner Gaea 2:
author .terrain projects, validate them in Gaea, build and export.
```

**Topics**（决定别人能否搜到）
```
mcp  model-context-protocol  gaea  quadspinner  terrain  heightmap
dem  procedural-terrain  ai-agent  claude  win32  ui-automation
```

**About 里勾选**：Releases / Packages 视情况

**建议加一个 Release**：`v1.0.0`，附上 `README.md` 里的要点作为说明。

---

## 五、分享时值得强调的三点

这个项目的差异化价值在于**它纠正了公开工具的错误结论**：

1. **`Gaea.Swarm.exe` 的 `IOException: 句柄无效` 不是"无害错误"**
   —— 真实原因是浮动授权被 GUI 占用，**构建根本没运行**。
   公开的 Gaea MCP 工具把它写成了"不代表文件损坏"，导致使用者以为成功。

2. **`Erosion2` 必须带 `Version: 2`**
   —— 缺它触发 Gaea 的旧格式迁移 → 空引用 → 错误沿下游传播，
   表现为"所有节点都报 `port In returned bad or no data`"。
   这是手写 `.terrain` 失败的第一大原因。

3. **侵蚀掩膜必须 16-bit 灰度**
   —— 8-bit/调色板 PNG 被误读为 16-bit（日志
   `Requested: N, Received: 2N`），掩膜只部分生效且**不报错**。

这三点在 README 与 `skill/gaea-terrain/reference/TROUBLESHOOTING.md` 里都有
完整的症状→原因→修复对照。

---

## 六、我还能替你做的

告诉我你选了哪个方案，我可以：

- 用 `gh` 或 token 直接**完成初始化、提交与推送**
- 补 `CHANGELOG.md`、`CONTRIBUTING.md`、GitHub Actions（`pytest` + `ruff`）
- 把 Skill 包单独拆成一个可被 AI 客户端直接拉取的目录结构
- 加一段英文 README（面向国际受众，你的参考文档已是英文）

同时，README 里标注的那个**未验证项**（自动打开工程依赖前台键盘事件）
是开源前值得修的：把按键发送移入 C# 助手即可，需要我继续的话说一声。
