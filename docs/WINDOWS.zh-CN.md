# Windows 支持与限制

**简体中文** · [English](WINDOWS.md) · [主页](../README.md)

> **状态（2026-10-20）**：Windows 桌面版已在一台真实 Windows 机器上完成走查，
> 安装包由 CI 构建。正式对外随 **0.4.0** 发布；0.3.0 及更早版本没有 Windows 资产。
>
> 本文说明支持范围、能做什么、已知边界和排障方法。科学方法学与格式限制
> （能量不可跨打分函数比较、PDBQT 无键级等）与 Linux 版完全相同，见
> [USER_GUIDE.zh-CN.md](USER_GUIDE.zh-CN.md)；更深的实现细节在源码树的
> `docs/TECHNICAL_GUIDE.md`。

---

## 1. 支持范围

| 项目 | 要求 / 说明 |
|---|---|
| 操作系统 | Windows 10 1809（build 17763）及以上，或 Windows 11 |
| 架构 | x64（不支持 ARM64） |
| 安装方式 | Inno Setup 安装包；按机器安装到 `C:\Program Files\VinaStudio`，**需要管理员权限** |
| 安装包体积 | 约 230 MB |
| 显卡 | 支持 Direct3D 11 的 GPU（Intel / NVIDIA / AMD 均可）；WebGL 经 ANGLE 走 D3D11 |
| 对接后端 | 随包的 **AutoDock Vina 1.2.7 命令行二进制**（Apache-2.0） |
| 发布状态 | **0.4.0 起**；当前开发树产出的安装包已通过真机走查 |
| 代码签名 | **未签名**（首次运行会触发 SmartScreen 提示，见 §2） |

安装包内已经包含 Python 运行时、科学计算栈和 Vina 引擎，**用户不需要安装
Python、uv、Node.js 或 pnpm**。

---

## 2. 安装

1. 从发布页下载 `vinastudio-<版本>-setup.exe`，并核对页面给出的 SHA-256。
2. 双击运行。因为安装包未做代码签名，Windows SmartScreen 可能提示
   “Windows 已保护你的电脑”——选择“更多信息 → 仍要运行”。
3. 安装器会检查 VC++ 2015–2022 x64 运行时；检测不到时会给出微软官方下载地址。
   应用包内也带了一份运行时 DLL，但系统级运行时仍是推荐配置。
4. 安装完成后从开始菜单或桌面图标启动；首次启动按向导选择工作区目录。
5. 安装器界面只有英文（Inno Setup 没有随附的简体中文语言文件）；应用界面
   本身中英双语，不受影响。

静默安装（部署脚本用）：

```powershell
vinastudio-0.4.0-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```

---

## 3. 能做什么

Windows 版包含与 Linux 版相同的应用功能：

- 受体 / 配体准备（PDB、mmCIF、MOL、SDF、MOL2、SMILES、内置 2D 画板）；
- 包围盒与结合位点定义、候选位点检测、逐点对接排序；
- 单配体对接、批量对接、虚拟筛选，实时进度、流式日志与真正的取消；
- Vina 与 Vinardo 打分；AutoDock4 需要外部地图（见 §4.1）；
- 姿态排序、几何校验、Redocking RMSD、聚类、相互作用指纹、2D 相互作用图；
- 作业历史、项目保存/恢复、CSV / HTML / 结果包导出；
- 中英双语、明暗主题、环境自检与渲染器诊断。

### 对接后端：`vina-cli`

上游 `vina` Python 模块**没有 Windows 分发**（PyPI 只有 manylinux 轮子，
conda-forge 只有 Linux / macOS 构建）。因此 Windows 版自动改用随包的
`vina.exe`：

- 引擎仍是 AutoDock Vina **1.2.7**，参数与 Linux 的 Python API 逐项对应；
- 固定种子下，命令行后端与 Python API 在 1iep 上逐构象能量一致；
- 「环境自检」页会显示后端为 `vina-cli`，原因 `module-missing`；依赖表里
  `vina` 一行仍如实写“导入失败”，但**能力判定是“可以运行对接”**——
  导入失败与能不能对接是两件事；
- 交互式“打分 / 优化 / 随机化”也走这个二进制。

---

## 4. 已知限制

### 4.1 AutoDock4（`ad4`）需要外部地图

与 Linux 版相同：本项目不随包分发 `autogrid4`，因此 `ad4` 只能用**已经生成好的**
AutoGrid4 地图打分，不能现场生成网格。界面对 `ad4` 标记 `nativeMaps: false`，
交互式打分/优化/随机化也会拒绝它。Vina 与 Vinardo 不受影响。

### 4.2 抗锯齿默认关闭

QtWebEngine 6 在 Windows 上的 WebGL 合成器存在已知的无规律闪屏问题；3Dmol 的
抗锯齿路径又会把绘制缓冲放大到 2 倍（像素数 4 倍），显著加重合成压力。为了
默认可用，**抗锯齿默认关闭**：

- 想恢复平滑边缘：设置 → 渲染质量 → 关闭“强制关闭抗锯齿”；
- 恢复后如果出现无规律闪屏，那是上述上游合成器问题，不是对接计算的问题；
- 该默认值对所有平台生效；旧版设置会自动迁移一次，之后手动选择保留。

### 4.3 安装包未签名，也没有自动更新

- 首次运行会触发 SmartScreen；这是未签名的正常表现。
- 应用不检查更新；升级请下载新安装包覆盖安装。
- 安装包按机器安装（`Program Files`），需要管理员权限；卸载走“应用和功能”。

### 4.4 安装器界面只有英文

应用界面中英双语；只有安装器的几屏是英文（Inno Setup 没有随附简体中文）。

### 4.5 平台覆盖

- 仅 x64；不支持 Windows ARM64、Windows 7/8。
- macOS 目前**只有源码运行路径**，没有安装包，也未做发布级验证。
- 真机走查目前覆盖一台 Intel UHD（D3D11）机器；其他 GPU / 驱动组合尚未逐一验证。
  环境自检页会显示实际渲染器，遇到异常请附上该字符串。

### 4.6 交互式操作是同步的

“打分 / 优化 / 随机化”在 Windows 上通过命令行二进制执行，请求会一直等到
计算结束才返回（与 Linux 的 Python API 调用同样是阻塞的）。对接作业本身仍在
子进程中运行，可取消，不阻塞界面。

### 4.7 网络与文件

- 应用只监听回环地址，不对外开放端口；按名称从 PubChem 取构象需要外网。
- 上传文件默认上限 100 MB（`VINASTUDIO_MAX_UPLOAD_MB`）。
- 中文/非 ASCII 路径已支持（0.4.0 修复了此前的读取失败）。

### 4.8 科学口径不变

不同打分函数的能量**不可直接比较**；预测亲和力不是实验结合自由能；
PDBQT 只保留重原子与极性氢，原子数减少是格式的正常行为。这些与操作系统无关。

---

## 5. 排障

应用内「使用帮助」支持搜索；失败卡片和警告上的帮助入口覆盖 SmartScreen 与
抗锯齿闪烁，并给出与本页一致的安全建议。

| 现象 | 处理 |
|---|---|
| 对接一直停在 0%、CPU 接近 0 | 0.4.0 已修复（旧包的冻结进程启动缺陷）。确认安装的是 0.4.0+ 并核对 SHA-256 |
| 运行期间弹出黑色 `vina.exe` 控制台窗口 | 0.4.0 已隐藏；旧包才会有 |
| 3D 视口无规律闪屏 | 保持“强制关闭抗锯齿”开启（默认）；若手动打开过 AA，闪屏属上游 QtWebEngine 合成器问题 |
| 视口卡顿 | 看“环境自检 → 实际渲染器”；若出现 `SwiftShader` / `Basic Render Driver`，说明落到了软件渲染。可试 `VINASTUDIO_SOFTWARE_RENDER=1` 做对照 |
| 中文路径导入配体失败 | 0.4.0 已修复；旧包会报 500 |
| 安装时提示缺少 VC++ 运行时 | 按提示安装微软官方的 VC++ 2015–2022 x64 运行时 |

**日志**：`%USERPROFILE%\.vinastudio\logs\vinastudio.log`
**工作区配置**：`%USERPROFILE%\.vinastudio\workspace.json`

**只读诊断脚本**（发布仓库 `packaging/windows/vinastudio-diagnostics.ps1`）：
先启动应用，再执行

```powershell
powershell -ExecutionPolicy Bypass -File .\vinastudio-diagnostics.ps1
```

输出包含显卡型号、驱动版本、OS build、安装包 SHA-256、日志副本，以及
`/api/system/info` 与 `/api/system/selfcheck` 的实时 JSON。不需要管理员权限。

---

## 6. 验证记录

- 真机走查：2026-10-20，Windows + Intel UHD（ANGLE / D3D11）；
  准备、对接、分析、持久化、中文路径、渲染器诊断均正常。
- 走查用的开发树安装包：`vinastudio-0.3.0-setup.exe`，229,564,630 B，
  SHA-256 `ec51d3d5e8448b2ab65b4a8a02dc88c25175e86aac80dac1ae81f2c9370bbb66`。
- **0.4.1 正式安装包（当前）**：`vinastudio-0.4.1-setup.exe`，229,553,518 B，
  SHA-256 `953ed0971f368b00479ed19d774fb1e776459a5da693adf7a2d80e85b287a77e`，
  由 tag `v0.4.1`（`a508f13`）构建；应用代码与 0.4.0 相同，另含依赖安全更新；
  0.4.0 安装包已被取代。
- 构建内自动冒烟：每个 Windows 构建都会在冻结包里真跑一次 1iep 对接
  （穷举度 1），断言完成、至少一个构象、亲和力为负；0.4.0 构建结果
  `-8.593 kcal/mol`、15.31 s（run `39544666349`），0.4.1 构建通过同一冒烟
  （run `39547459457`）。这同时覆盖了进程 spawn、stdout 重定向、CLI 后端与
  随包 Vina 二进制。
- Linux 资产：0.4.1 由 run `39554364290` 构建（0.4.0 为 `39545746608`）。

---

## 7. English summary

Windows is a supported desktop platform from **0.4.0**: an Inno Setup installer
for Windows 10 1809+ / 11 on x64, verified on real hardware. The application
bundles Python, the scientific stack, and the AutoDock Vina 1.2.7 command-line
engine, so no separate runtime is needed. Docking automatically uses that binary
because the `vina` Python module has no Windows build. Known boundaries:
AutoDock4 requires externally generated AutoDock4 maps; antialiasing is off by
default because of a QtWebEngine compositor flicker with AA enabled; the
installer is unsigned (SmartScreen) and has no auto-update; only x64 is
supported and macOS remains source-only. See the sections above for
troubleshooting and verification details.
