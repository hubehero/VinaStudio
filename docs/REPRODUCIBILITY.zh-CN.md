# 可复现性与发布核验

[English](REPRODUCIBILITY.md) · **简体中文**

本页说明 VinaStudio 的一个发布版本能证明什么、如何核验下载的资产，以及软件
验证证据放在哪里。它刻意与科学结论分开：可复现的构建不代表通用对接准确率。

## 发布来源

从 v0.7.0 起，每个 GitHub Release 附带：

| 资产 | 用途 |
|---|---|
| `SHA256SUMS` | Linux tar.gz、`.deb` 与 Windows 安装包的 SHA-256 |
| `BUILD-MANIFEST.json` | tag、源码 commit、CI run URL、构建时间、Python 版本、各资产大小与 SHA-256 |

清单由打 tag 的 CI 运行生成并随资产上传；v0.7.0 的清单是发布后根据 GitHub
资产元数据补建的，工作流更新后的版本由 CI 生成。它是来源记录，不是签名；
Windows 安装包仍未签名，SmartScreen 仍可能拦截。

## 核验发布资产

下载 `SHA256SUMS` 和准备运行的资产，在执行前核对校验和：

```bash
sha256sum -c SHA256SUMS
```

`BUILD-MANIFEST.json` 记录同样的哈希，以及 tag、commit 和 workflow run。
将其中的 `tag`、`commit` 与发布页对照；不一致就不要使用该资产。

## 重跑软件检查

**发布树有意不包含测试套件**，以减小公开源码体积并避免分发不属于运行时的
测试夹具。完整 pytest 在开发树运行：

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check .
pnpm -C web typecheck
pnpm -C web test
```

发布树内的轻量公开后端 smoke 为：

```bash
uv run python validation/ci/smoke.py
```

smoke 覆盖健康检查、工作区初始化、文件识别、配体准备、盒子计算和只读诊断，
不依赖 Qt、网络或完整对接；它不能替代开发树测试。

## 验证证据

| 问题 | 证据 |
|---|---|
| 准备流程是否复现 1IEP 上游产物？ | `validation/manifest.json` 与开发树 `tests/` |
| 已提交的 1IEP 对照能否重对接？ | `docs/ACADEMIC_VALIDATION.md`、`validation/benchmark/records/` |
| 开放靶点与 PoseBusters 的限制是否记录？ | `validation/benchmark/README.md` 及其记录 |
| 没有桌面壳时 API 是否可用？ | `validation/ci/smoke.py` 与开发树 API 集成测试 |

验证记录会说明自身限制。本项目不据此声明 PDBbind/CASF 性能、富集能力、实验
结合自由能或通用准确率。

## 独立复现清单

1. 检出 `BUILD-MANIFEST.json` 中指定的 tag 或 commit。
2. 运行上面的开发树检查，并与发布说明对照。
3. 运行 1IEP 对照，比较 top pose 与亲和力是否落在记录范围内。
4. 至少再运行一个未包含在仓库示例中的体系。
5. 记录操作系统、Python、Vina 版本、输入哈希和任何偏差。
6. 结果与记录不一致时，提交 **复现报告** issue；模板要求 tag、manifest commit、
   命令和已脱敏日志。

项目目前只有一位维护者，也没有第三方复现记录。这是证据边界，不是隐藏的
正确性声明；复现失败时请附上完整命令和环境报告。
