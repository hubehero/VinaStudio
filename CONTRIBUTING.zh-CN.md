# 为 VinaStudio 做贡献

**简体中文** · [English](CONTRIBUTING.md)

感谢你愿意花时间参与。VinaStudio 是个小项目，最有价值的贡献是**能复现的缺陷
报告、聚焦的修复和文档改进**——不需要是分子对接专家也能帮上忙。

## 项目放在哪里

这个仓库是**发布通道**：它携带应用源码、打包脚本和公开文档。开发树另有一套，
包含测试套件、测试夹具和热重载流程，所以这里看不到 `tests/`。

如果你的改动需要测试，请把它一并放进 PR；维护者会在开发树里跑完整套件后再合并。
超过一行的改动，建议先开 issue 对齐方案。

## 报告缺陷

能复现的报告比长篇描述有用得多。请附上：

1. VinaStudio 版本（状态栏和“关于”页都有）；
2. 操作系统及版本；
3. **环境自检 → 实际渲染器**那一行原文；
4. 复现步骤；
5. 你期望发生什么、实际发生了什么；
6. `~/.vinastudio/logs/vinastudio.log` 的相关片段（Windows 上是
   `%USERPROFILE%\.vinastudio\logs\vinastudio.log`），并去掉其中的个人路径。

如果问题与某个结构有关，一个最小的输入文件非常有帮助；请不要上传你无权分享的
文件。

## 功能建议

请描述你想解决的问题，而不只是你想到的方案。具体的工作流——“我想让十个配体
对同一个受体各跑一次，并导出一张表”——比抽象的功能名更容易落地。

## 拉取请求

1. Fork 仓库，从 `main` 建分支；
2. 保持改动聚焦，不相关的修复分开提交；
3. 遵循现有代码风格；
4. 行为变化时同步更新文档；面向用户的改动写进 `CHANGELOG.md` 的
   `[Unreleased]`；
5. PR 里用几句话说明问题与修法；
6. 确保本地能跑的检查都通过。

评审先看正确性，再看改动是否符合项目的科学口径。小而清楚的补丁比大范围重写更
容易合并。

## 开发环境

公开树可以构建应用：

```bash
git clone https://github.com/<你的用户名>/VinaStudio.git
cd VinaStudio

uv sync --extra dev
pnpm -C web install
pnpm -C web build
```

运行这里有的检查：

```bash
uv run ruff check .
pnpm -C web typecheck
pnpm -C web build:checked
```

准备发布时不要在发布检出里使用 `uv run`：它会重新解析环境，可能把 `uv.lock`
重锁成本机镜像。发布脚本请直接用解释器运行。

## 代码风格

### Python

- 以 Python 3.12 为目标；类型标注用来把契约说清楚，不做装饰；
- `vinastudio/core/` 不导入 Qt 与 FastAPI，必须能脱离显示器测试；
- 领域错误从 `vinastudio.core.errors` 抛出，由 API 统一映射；
- 注释解释**为什么**，不复述代码在做什么。

### TypeScript 与 Vue

- Vue 3 + `<script setup>` + Composition API；
- 契约类型放在 `web/src/types/api.ts`；
- 运行 `pnpm -C web typecheck`——生产构建会剥离类型而不检查。

### 文档

- 面向用户的文档成对提供：英文 `NAME.md`、简体中文 `NAME.zh-CN.md`，每对顶部
  互相跳转；
- 新增页面时同步更新 README 的文档表；
- 公开文档里不写内部任务编号或流程叙述。

## 提交信息

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

```
feat: add SMILES input support
fix: correct the ligand type for a one-residue peptide
docs: explain the Windows antialiasing default
```

一个提交说清一件事；需要展开的解释放进正文，不要塞进主题。

## 翻译

应用界面中英双语，主要文档也有两份。改动用户可见文案时，同时更新
`web/src/i18n/locales/zh-CN.ts` 与 `en-US.ts`；改动文档时也请更新对应语言版本，
或在 PR 里注明翻译待补。

## 行为准则

参与本项目即受 [CODE_OF_CONDUCT.zh-CN.md](CODE_OF_CONDUCT.zh-CN.md) 约束。
请保持尊重；技术分歧欢迎，人身攻击不行。

## 安全

请不要在公开 issue 里报告漏洞，按 [SECURITY.zh-CN.md](SECURITY.zh-CN.md)
私下报告。

## 许可证

参与贡献即表示你同意以 MIT 许可证授权你的贡献，与本项目一致。
