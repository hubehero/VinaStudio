# 发布 VinaStudio

**简体中文** · [English](RELEASING.md)

> 本页是维护者的发布流程。英文版是完整规范；这里给出同样的步骤与判据，方便中文维护者照着做。
> 发布规则由 `packaging/ci/release-preflight.py` 自动检查，**预检不过就不要打 tag**。

## 两条最容易犯的规则

- **版本号必须是已发布版本的下一个**（补丁 / 小版本 / 大版本之一）。版本号描述的是
  “第几次发布”，不是内部里程碑的编号；不要跳号，也不要为了对齐里程碑改号。
- **发布说明由人写进 [`CHANGELOG.md`](CHANGELOG.md)**。发布页正文从对应小节提取，
  不从 commit 标题生成。只写用户能感知的功能、变化与修复，不写内部任务编号或工作流叙述。

## 步骤

### 1. 看已经发布了什么

```bash
gh release list
```

新版本号以这份列表为准。然后用脚本同步所有版本位置（`pyproject.toml`、包版本、
前端、Debian control、`uv.lock`）：

```bash
python packaging/ci/bump-version.py --version 0.4.0
```

### 2. 写 CHANGELOG 小节

把 `## [Unreleased]` 下的条目移到新的 `## [0.4.0] - YYYY-MM-DD` 小节，
`[Unreleased]` 留空；补上遗漏的用户可见变化。标题沿用 Keep a Changelog 的
`Added` / `Changed` / `Fixed`，需要时加 `Out of scope`。中英双语都写。

### 3. 跑预检

```bash
python packaging/ci/release-preflight.py
```

它会列出已发布版本，然后检查版本序列、CHANGELOG 小节、公开措辞、发布树、
版本单一来源、提交身份、发布工作流、安全告警与导入完整性。**有失败就不要打 tag。**

### 4. 先构建，再打 tag

推送分支并手动触发工作流。Release 只在 tag 上真正发布，所以这一步不会对外发布：

```bash
git push origin main
gh workflow run release.yml
```

等它变绿——这是发现构建问题最便宜的地方。

Windows 安装包也要从同一个 commit 构建并验证：

```bash
gh workflow run windows-build.yml --ref main
# 等运行结束，下载 windows-installer，确认日志里有 "docking OK"
```

0.4.1 的安装包是手动挂载的。0.5 的目标是把 `build-windows` 加进 `release.yml`，
tag 后自动构建并挂载；在此之前，仍把验证过的安装包在创建 release 后手动挂上去，
并在说明里写 SHA-256。

### 5. 打附注 tag 并推送

```bash
git tag -a v0.4.0 -m "VinaStudio 0.4.0"
git push origin v0.4.0
```

### 6. 核对发布结果

- 发布页正文是对应的 CHANGELOG 小节，不是裸的比较链接；
- 资产文件名带新版本号，哈希与构建日志一致；
- `preflight` 与 `build-linux`（以及 Windows 构建）都是绿的。

## 安全告警

仓库由 Dependabot 与 CodeQL 扫描。**有 high / critical 告警时预检会拒绝发布**。
处理方式只有两种，**不是关掉扫描器**：

- **修掉**：CodeQL 会在 push 后重扫，下一次运行确认修复；
- **带理由忽略**：理由就是审计线索，Security 页会保留告警、忽略记录与理由。

`py/path-injection` 一族的分类写在 `.github/codeql/codeql-config.yml`：桌面端把用户在
文件对话框里选的绝对路径交给后端，这是 API 的契约；必须限制在根内的路径走
`core/paths.resolve_within`。发布前先看 Security 页，不要等构建失败才看。

`engine-check.yml` 的两个 job 也要绿；Windows job 是“Windows 能对接”的 CI 证据。

## CI 做什么

`v*` tag 上，`.github/workflows/release.yml` 依次运行：

| Job | 作用 |
|---|---|
| `preflight` | 与第 3 步相同的检查（`--allow-published`，因为 tag 已存在） |
| `build-linux` | 前端构建、PyInstaller、`.deb` 与 tar.gz |
| `create-release` | 用 CHANGELOG 正文创建 GitHub Release |

预检失败会挡住整条链，不合规的发布发不出去。

## 发布资产

| 资产 | 目标 |
|---|---|
| `vinastudio_X.Y.Z_amd64.deb` | Ubuntu / Debian（amd64） |
| `vinastudio-X.Y.Z-linux-amd64.tar.gz` | 便携包，解压后运行 `vinastudio/vinastudio` |
| `vinastudio-X.Y.Z-setup.exe` | Windows 10 1809+ / 11，x64（0.4.0 起） |

Linux 需要 OpenGL 桌面会话；Windows 需要 Direct3D 11，按机器安装（管理员），
安装包未签名（SmartScreen 会提示）。科学栈（vina、meeko、RDKit）与 Vina 1.2.7
命令行二进制都已随包；Windows 没有 `vina` Python 模块，会自动使用该二进制。
**macOS 不发布 release 包**（2026-10-21 决定）；仅保留源码路径，不做安装包、
签名或公证。
