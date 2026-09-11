<!-- Language / 语言 -->
**🌐 语言:** [English](README.md) &nbsp;|&nbsp; **简体中文**

# gaea-mcp — 让 AI 真正驱动 Gaea 2 的 MCP Server

> 一套能**跑通**的 QuadSpinner Gaea 2 自动化工具：MCP Server + 可直接安装的
> Skill 包。不是"生成 .terrain 文件"的玩具，而是**从真实高程数据到成功导出成品**
> 的完整链路。

**验证状态**：本工具包使用的每一种文件格式、节点参数集与构建流程，都在
**Gaea 2.3.0.1 (Windows)** 上实测通过，并成功导出过真实的 4096² 高度图与彩色图。

### 已验证 / 未验证 —— 请务必阅读

| 能力 | 状态 |
|---|---|
| `.terrain` 生成（`$id` 图、必需端口、`Version:2`、Export 路径） | ✅ 离线自检 8 组全部通过 |
| 16-bit 灰度掩膜写入 + 位深防护 | ✅ 实测湖面 7.150 m，标准差 0.0 mm |
| 高度图/掩膜读写、归一化、晕渲、分形地形 | ✅ 已验证 |
| 真实 DEM 下载（Copernicus GLO-30） | ✅ 已用已知真值核对 |
| **让 Gaea 加载并校验工程**（`gaea_validate_in_gaea`） | ⚠️ **部分验证**。基于日志的判定可靠；自动 `Ctrl+O` 打开在部分主机上无效 |
| **触发构建**（`gaea_build`） | ⚠️ **未完整验证**。构建序列已人工驱动并成功导出，但依赖上面的打开步骤 |

**已知限制**：自动"打开工程"依赖向 Gaea 发送前台键盘事件（`Ctrl+O`）。在 Windows 上，
后台进程常被前台锁定策略拒绝输入——`SetForegroundWindow` 可能报告成功，但
`SendInput` 根本没进目标窗口。目前已有"最小化+还原"兜底与"已加载则短路"，
但**未能在所有主机上复现成功**。

变通方案：由人手动 `File ▸ Open` 打开工程一次即可，`gaea_build` 所需的构建设置面板
与按钮调用不受此限制。彻底的修法是把按键发送移入 C# 助手——它与窗口激活同进程。

---

## 为什么需要它

公开可得的同类工具普遍**生成 Gaea 打不开、或能打开但无法构建的 `.terrain`**。
其中一个项目自己的文档里写着：

> "The CLI subprocess encounters **handle is invalid** errors that do not
> indicate actual file corruption."

它把 `Gaea.Swarm.exe` 的必然崩溃解读成了"无害"。**这个结论是错的**，而这正是
无数人卡住的地方。真实情况是：

| 现象 | 真实原因 |
|---|---|
| `Gaea.Swarm.exe` 报 `IOException: 句柄无效` | **浮动授权被 GUI 占用**。只有 GUI 能先释放它，Swarm 才能运行 |
| 构建无产出、无报错、exit 0 | 图里**没有 `Export` 节点**，Gaea 认为无事可做 |
| `port In returned bad or no data` | 上游某节点**拒绝了参数** —— 最常见是 `Erosion2` 缺 `Version: 2` |
| 所有节点都报错 | Gaea 会**把单个错误沿下游传播**。修**第一个**，不是最后一个 |
| 掩膜只部分生效 | 掩膜被写成 8-bit 或调色板，Gaea 按 16-bit 读取。**必须 16-bit 灰度** |

本工具把以上全部固化为默认行为与防护检查。

---

## 安装

```bash
# 需要 Python 3.10+ 与 .NET 8 SDK（后者用于编译 GUI 助手）
pip install -e .

# 预检：能否找到 Gaea、能否编译助手、能否连上 GUI
gaea-doctor
```

`gaea-doctor` 会输出安装路径、版本、许可类型、构建/缓存/日志目录，并检查已知陷阱。
**在做任何其他事情之前先跑它。**

### 接入 AI 客户端

```json
{
  "mcpServers": {
    "gaea": {
      "command": "gaea-mcp"
    }
  }
}
```

---

## 工具列表

| 工具 | 作用 |
|---|---|
| `gaea_doctor` | **先跑这个**。安装、版本、许可、目录、GUI 状态、已知陷阱 |
| `gaea_list_node_types` | 本工具会生成的节点类型、端口与默认值，以及已知不可用清单及原因 |
| `gaea_create_project` | 生成可构建的 `.terrain`（自动补 `Version:2`、校验导出路径、拒绝危险节点） |
| `gaea_audit_project` | 离线结构校验：`$id` 图、必需端口、Export 路径、危险节点 |
| `gaea_summarise_project` | 读取并描述已有工程 |
| `gaea_validate_in_gaea` | **关键工具**。让 Gaea 加载工程并读它的日志，找出真实校验错误 |
| `gaea_build` | 经 UI 自动化触发构建并等待产物（`close_gui` 模式最可靠） |
| `gaea_read_build_report` | 读取最近一次构建报告 |
| `gaea_scan_logs` | 读 Gaea 的构建/会话日志并提取错误行 |
| `gaea_prepare_heightmap` | 把原始高程转成 Gaea 可读格式，并生成 16-bit 侵蚀掩膜与晕渲预览 |
| `gaea_make_fractal_heightmap` | 没有真实 DEM 时生成分形地形 |
| `gaea_fetch_copernicus_dem` | **下载真实高程**（GLO-30，AWS 公开数据，无需密钥） |
| `gaea_write_erosion_mask` | 生成 16-bit 灰度侵蚀掩膜（1=侵蚀，0=保护） |
| `gaea_render_preview` | 不打开 Gaea 也能看晕渲预览 |
| `gaea_open_in_gui` | 在 GUI 中打开工程供人查看 |

---

## 推荐调用顺序

```
gaea_doctor                      # 先确认环境
      ↓
gaea_fetch_copernicus_dem        # 真实地点（可选）
  或 gaea_make_fractal_heightmap
      ↓
gaea_prepare_heightmap           # 归一化 + 生成掩膜
      ↓
gaea_create_project              # 生成 .terrain
      ↓
gaea_validate_in_gaea            # ★ 让 Gaea 自己判断
      ↓
gaea_build                       # 触发构建
      ↓
gaea_read_build_report           # 校验产物
```

**不要跳过 `gaea_validate_in_gaea`。** 离线校验看不到 Gaea 加载器的全部要求，
跳过它就是在拿构建时间赌博。

---

## 写进代码的硬性约束

### `Terrain.Height` 是**起伏量**，不是 Y 尺寸

```
Terrain.Width  = 地面跨度（米）
Terrain.Height = max_elevation - min_elevation    ← 起伏
Compression    = Height / Width
```

Gaea 默认 `Width=5000 / Height=2500`（比例 0.5）。**照搬到真实的 400 m 丘陵上，
会渲染出 2.5 km 的高山** —— 这是地形不真实的最常见来源。西湖群山的真实比例是
`12000 m / 415 m = 0.0346`。

### 归一化约定必须一致

```
0.0 ↔ 最低点        1.0 ↔ 最高点
norm = (metres - min_m) / (max_m - min_m)
```

### 位图导出用 `Export` 节点，不是 `Mesher`

```json
{"$type": "QuadSpinner.Gaea.Nodes.Export, Gaea.Nodes",
 "Format": "PNG16", "Location": "Explicit",
 "OutputPath": "D:/out/terrain_heightmap"}
```

`OutputPath` **不要带扩展名**，Gaea 会按 `Format` 追加。

### `Erosion2` 必须带 `Version: 2`

```json
{"Duration": 40.0, "Downcutting": 0.2, "Seed": 12345,
 "Enable": true, "Version": 2}
```

缺 `Version` 时，Gaea 会尝试旧格式迁移并空引用，随后所有下游节点都报
`port In returned bad or no data`。

### `RelativePath: true` 以工程所在目录解析

```json
{"FileName": "heightmap.png", "RelativePath": true}
```

数据文件必须与 `.terrain` 同目录。

### 侵蚀掩膜必须是 16-bit 灰度

8-bit 或调色板 PNG 会被误读为 16-bit：

```
WRN Array length doesn't conform Map resolution! Requested: 16777216, Received: 33554432
```

此时掩膜**只被部分应用**，被"保护"的区域仍会被侵蚀，且**不报错**。

### 水面要在数据里压平，再用掩膜保护

`Erosion2` 会侵蚀它被允许触及的一切。湖泊或平原必须在**进入 Gaea 之前**于数据中
压平，再用掩膜保护。两者结合才能得到数学上精确的水位
（实测：均值 7.150 m，标准差 0.0 mm）。

### 如何构建

```
Gaea.exe -Path <file>      ✗ 此构建上会崩溃
直接运行 Gaea.Swarm.exe      ✗ GUI 持有授权时必然 IOException
Ctrl+Shift+B               ✓ 构建快捷键（Ctrl+B 只打开设置面板）
GUI: Ctrl+B → Execute Build → "Start Build" | "Close Gaea and Build"
```

`Close Gaea and Build` 会关闭 GUI 以释放授权再构建 —— **最可靠**，也是单授权席位
共享时唯一可行的方式。

### 会拒绝手写参数的节点类型

`Thermal2` · `SatMap` · `WaterColor` · `Lake` · `Sea` · `Rivers` · `Thermal`

它们并非不可用，而是**参数集未知**。要用的话，先在 GUI 里添加该节点、设好参数、
保存，再把导出的 JSON 原样抄回来。

---

## 目录结构

```
gaea_mcp/
├─ pyproject.toml
├─ README.md / README.zh-CN.md   文档（英/中）
├─ LICENSE / NOTICE.md           MIT + 第三方声明
├─ selftest.py                   离线自检（无需 Gaea）
├─ acceptance.py                 端到端验收（让 Gaea 加载生成的工程）
├─ skill/                        可安装的 AI Skill 包
│  └─ gaea-terrain/
│     ├─ SKILL.md
│     └─ reference/
│        ├─ FILE_FORMAT.md
│        ├─ NODES.md
│        ├─ BUILD.md
│        └─ TROUBLESHOOTING.md
└─ src/gaea_mcp/
   ├─ config.py                  探测安装、版本、许可、目录
   ├─ terrain.py                 .terrain schema + 生成器 + 结构审计
   ├─ outputs.py                 高度图/掩膜读写、归一化、晕渲、分形 DEM
   ├─ uia.py                     UI Automation 桥（自动编译 C# 助手）
   ├─ gaea.py                    启动/加载/构建/读报告 编排
   ├─ server.py                  MCP 工具定义
   ├─ doctor.py                  命令行预检
   └─ uia/uia.cs                 C# 助手，按控件名驱动 Gaea
```

## 自检

```bash
python selftest.py      # 离线：文件格式、$id 图、掩膜位深、防护检查
python acceptance.py    # 在线：让 Gaea 加载生成的工程并报告结果
```

## 许可

MIT —— 见 [LICENSE](LICENSE)。第三方与商标声明见 [NOTICE.md](NOTICE.md)。

本项目是**独立的非官方集成**，与 QuadSpinner 无隶属关系，不含其任何代码或资源。
使用需要你自己持有有效的 Gaea 2 授权。
