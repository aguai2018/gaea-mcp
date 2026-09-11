# gaea-mcp — 让 AI 真正驱动 Gaea 2 的 MCP Server

> 一套能**跑通**的 QuadSpinner Gaea 2 自动化工具：MCP Server + Skill 包。
> 不是"生成 .terrain 文件"的玩具，而是**从真实 DEM 到成功导出成品**的完整链路。

**验证状态**：本工具包使用的每一种文件格式、节点参数、构建流程，都在
**Gaea 2.3.0.1 (Windows)** 上实测通过，并成功导出过 4096² 高度图与彩色图。

### 已验证 / 未验证（务必阅读）

| 能力 | 状态 |
|---|---|
| `.terrain` 生成（`$id` 图、必需端口、`Version:2`、Export 路径） | ✅ 离线自检 8 组全通过 |
| 16-bit 灰度掩膜写入与位深防护 | ✅ 已验证；实测湖面 7.150 m / 标准差 0.0 mm |
| 高度图/掩膜读写、归一化、晕渲、分形地形 | ✅ 已验证 |
| 真实 DEM 下载（Copernicus GLO-30） | ✅ 已验证（12 km / 2048²，面积与高程经真值核对） |
| **让 Gaea 加载并校验工程**（`gaea_validate_in_gaea`） | ⚠️ **部分验证**。读日志判定逻辑可靠；但自动按 `Ctrl+O` 打开工程在部分环境下无效（见下） |
| **触发构建**（`gaea_build`） | ⚠️ **未完整验证**。构建序列本身已人工跑通并成功导出；但其依赖的打开工程步骤同上 |

**已知限制**：自动"打开工程"依赖向 Gaea 发送前台键盘事件（`Ctrl+O`）。
在 Windows 上，后台进程常被前台锁定策略拒绝输入——即使
`SetForegroundWindow` 报告成功，`SendInput` 也可能不进目标窗口。
本项目已加"最小化+还原"兜底与工程已加载短路，但**未能在所有环境复现成功**。

workaround：由人手动在 Gaea 里打开工程（`File ▸ Open`）**一次**，
之后 `gaea_build` 所需的 `Ctrl+B` 构建设置面板与按钮调用不受此限制。
更好的修法是把按键发送也移入 C# 助手（它与窗口激活在同一进程）。

---

## 为什么需要它

公开可得的同类工具普遍**生成了 Gaea 打不开、或能打开但构建失败的 `.terrain`**。
它们的文档里甚至写着：

> "The CLI subprocess encounters **handle is invalid** errors that do not
> indicate actual file corruption."
> —— 把 `Gaea.Swarm.exe` 的必然崩溃解释成了"不影响文件正确性"

这个判断是**错的**，也正是无数人卡住的地方。真实情况是：

| 现象 | 真实原因 |
|---|---|
| `Gaea.Swarm.exe` 报 `IOException: 句柄无效` | **浮动授权被 GUI 占用**。必须由 GUI 释放授权后再构建 |
| 构建"无产出且无报错"(exit 0) | 工程里**没有 `Export` 节点**，Gaea 认为无事可做 |
| `port In returned bad or no data` | 上游某节点**参数不被接受**（最典型：`Erosion2` 缺 `Version: 2` 触发旧格式迁移） |
| 一切节点都报错 | Gaea 会**沿下游传播**单个错误。修**第一个**，不是最后一个 |
| 掩膜"部分生效" | 掩膜存成 8-bit/调色板 PNG，被误读为 16-bit。**必须 16-bit 灰度** |

本工具把这些全部编码成了默认行为与防护检查。

---

## 安装

```bash
# 1) 需要 Python 3.10+ 与 .NET 8 SDK（后者用于编译 GUI 自动化助手）
pip install -e .

# 2) 自检：确认能找到 Gaea、能编译助手、能连上 GUI
gaea-doctor
```

`gaea-doctor` 会输出安装路径、版本、许可类型、构建/缓存/日志目录，
并检查已知陷阱。**在任何其他操作之前先跑它。**

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

## 可用工具

| 工具 | 作用 |
|---|---|
| `gaea_doctor` | **先跑这个**。探测 Gaea 安装、版本、许可、目录、GUI 状态、已知陷阱 |
| `gaea_list_node_types` | 列出可安全使用的节点类型、端口、默认参数，以及**已知不可用**的类型及原因 |
| `gaea_create_project` | 生成可构建的 `.terrain`（自动加 `Version:2`、校验导出路径、拒绝危险节点） |
| `gaea_audit_project` | 离线结构校验：`$id` 图、必需端口、Export 路径、危险节点 |
| `gaea_summarise_project` | 读取并描述已有工程（地形定义、构建定义、节点、连线） |
| `gaea_validate_in_gaea` | **关键**。让 Gaea 自己加载工程并读它的日志，找出真实校验错误 |
| `gaea_build` | 通过 UI 自动化触发构建并等待产物（默认 `close_gui` 模式，最可靠） |
| `gaea_read_build_report` | 读取最近一次构建报告（`report.json`） |
| `gaea_scan_logs` | 读 Gaea 的构建日志 / 会话日志，并提取错误行 |
| `gaea_prepare_heightmap` | 把原始高程转成 Gaea 可读格式（16-bit PNG / `.r32`），生成 16-bit  erosion 掩膜与晕渲预览 |
| `gaea_make_fractal_heightmap` | 没有真实 DEM 时生成分形地形 |
| `gaea_fetch_copernicus_dem` | **下载真实高程**（Copernicus DEM GLO-30，AWS 公开数据，无需密钥），按中心经纬度切正方形米制窗口 |
| `gaea_write_erosion_mask` | 生成 16-bit 灰度侵蚀掩膜（1=侵蚀, 0=保护） |
| `gaea_render_preview` | 不打开 Gaea 也能看晕渲预览 |
| `gaea_open_in_gui` | 在 GUI 中打开工程供人查看 |

---

## 推荐调用顺序

```
gaea_doctor                      # 先确认环境
      ↓
gaea_fetch_copernicus_dem        # 有真实地点时（可选）
  或 gaea_make_fractal_heightmap
      ↓
gaea_prepare_heightmap           # 归一化 + 生成掩膜（如需保护湖区/平原）
      ↓
gaea_create_project              # 生成 .terrain
      ↓
gaea_validate_in_gaea            # ★ 关键：让 Gaea 自己说行不行
      ↓
gaea_build                       # 触发构建
      ↓
gaea_read_build_report           # 校验产物
```

**不要跳过 `gaea_validate_in_gaea`。** 离线校验看不到 Gaea 加载器的全部要求，
跳过它就是在拿构建时间赌博。

---

## 关键约束（写进代码的硬知识）

### 地形定义：Gaea 的 `Height` 是**起伏**不是 Y 尺寸

```
Terrain.Width  = 地面跨度（米）
Terrain.Height = max_elevation - min_elevation   ← 起伏量
Compression    = Height / Width
```

Gaea 默认 `Width=5000 / Height=2500`（比例 0.5）。**照搬会把 400 m 的丘陵渲染成 2.5 km 的高山** —— 这是最常见的不真实来源。
西湖群山真实比例是 `12000 m / 415 m = 0.0346`。

### 归一化约定必须与工程一致

```
0.0 ↔ 最低点        1.0 ↔ 最高点
norm = (metres - min_m) / (max_m - min_m)
```

### 位图导出用 `Export` 节点，不是 `Mesher`

```json
{"$type": "QuadSpinner.Gaea.Nodes.Export, Gaea.Nodes",
 "Format": "PNG16", "Location": "Explicit",
 "OutputPath": "D:/out/terrain_heightmap"}     // 不要带扩展名
```

### `Erosion2` 必须带 `Version: 2`

```json
{"Duration": 40.0, "Downcutting": 0.2, "Seed": 12345,
 "Enable": true, "Version": 2}
```

缺 `Version` → Gaea 尝试旧格式迁移 → `Object reference not set to an instance of an object`
→ 错误沿下游传播 → 所有消费者报 `port In returned bad or no data`。

### 数据文件用相对路径时必须与工程同目录

```json
{"FileName": "heightmap.png", "RelativePath": true}
```

### 侵蚀掩膜必须 16-bit 灰度

8-bit 或调色板 PNG 会被误读为 16-bit：

```
WRN Array length doesn't conform Map resolution! Requested: 16777216, Received: 33554432
```

此时掩膜**只被部分应用**，被"保护"的区域仍会被侵蚀。

### 想得到绝对平坦的水面，就在数据里压平

`Erosion2` 会侵蚀它被允许触及的一切。湖泊/平原应在**进入 Gaea 之前**于数据中压平，
再用掩膜保护，二者结合才能得到数学上精确的水位（实测：均值 7.150 m，标准差 0.0 mm）。

### 构建路径

```
Gaea.exe -Path <file>       ✗ 此构建上会崩溃，永远不要用
直接运行 Gaea.Swarm.exe      ✗ GUI 持有授权时必然 IOException
Ctrl+Shift+B                ✓ 构建快捷键（Ctrl+B 只打开设置面板）
GUI: Ctrl+B → Execute Build → "Start Build" | "Close Gaea and Build"
```

`Close Gaea and Build` 会关闭 GUI 释放授权再构建，**最可靠**，也是单授权席位
共享时唯一可行的方式。

### 已知会拒绝手写参数的节点（本工具会主动拒绝）

`Thermal2` · `SatMap` · `WaterColor` · `Lake` · `Sea` · `Rivers` · `Thermal`

它们并非"不可用"，而是**参数集未知**；若要用，必须先放一个到 GUI 里保存一次，
从导出的 JSON 反推正确参数，再写进工程。

---

## 目录结构

```
gaea_mcp/
├─ pyproject.toml
├─ README.md                     ← 本文件
├─ selftest.py                   离线自检（无需 Gaea）
├─ acceptance.py                 端到端验收（会让 Gaea 加载生成的工程）
├─ skill/                        可直接安装的 AI Skill 包
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
   ├─ outputs.py                 高度图/掩膜读写、归一化、晕渲、分形地形
   ├─ uia.py                     UI Automation 桥（自动编译 C# 助手）
   ├─ gaea.py                    启动/加载/构建/读报告 编排
   ├─ server.py                  MCP 工具定义
   ├─ doctor.py                  命令行预检
   └─ uia/uia.cs                 C# 助手（按控件名驱动 Gaea）
```

## 自检

```bash
python selftest.py      # 离线：文件格式、$id 图、掩膜位深、防护检查
python acceptance.py    # 在线：让 Gaea 加载生成的工程并报告是否通过
```

## 许可

MIT
