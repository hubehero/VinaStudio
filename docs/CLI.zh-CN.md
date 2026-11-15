# 无界面 CLI

**简体中文** · [English](CLI.md) · [主页](../README.md)

`vinastudio-cli` 不启动 Qt，也不启动 HTTP 服务，直接复用
`vinastudio.core` 做准备、对接、验证和导出。它不会 import 桌面外壳或 FastAPI，
与界面共用 `run_docking`/`prepare_*`。

## 安装

基础包 = core + CLI + 本地 API 服务；桌面外壳是可选 `desktop` extra：

```bash
pip install vinastudio                 # 仅 CLI/API
pip install "vinastudio[desktop]"      # 加上 Qt 桌面应用
```

源码开发：

```bash
uv sync --extra dev                    # 开发环境（含 Qt）
uv run vinastudio-cli version --json
```

`vinastudio` 无子命令仍启动桌面；无界面工作请用 `vinastudio-cli`（或
`vinastudio <子命令>`）。未安装 `desktop` extra 时，无子命令会提示安装并以
2 退出。

## 命令

| 命令 | 作用 |
|---|---|
| `prepare receptor -i rec.pdb -o prep/` | 受体 PDBQT/PDB + 报告 |
| `prepare ligand -i lig.sdf -o prep/` | 配体 PDBQT/SDF + 报告 |
| `dock --config job.json --out out/result.json` | 单次对接 + `result.json` |
| `screen --config screen.json --out ranking.csv` | 顺序筛选库 + 排行 |
| `validate --manifest manifest.json --out report/` | 重对接/交叉对接报告 |
| `export --result result.json --format complex-pdb,pml,cxc,plip-json --out exports/` | 姿态工件与互操作视图 |
| `server --host 127.0.0.1 --port 8000` | 无 Qt 的本地 FastAPI 服务 |
| `engines list/doctor --manifest engine.json` | 探测内置与外部引擎 |
| `version --json` | 软件与引擎版本 |

一次性命令支持 `--json`；此时 stdout 只有 JSON envelope，引擎进度写到 stderr。
`server` 是长驻服务，不使用该 envelope。

## `job.json`

路径相对 job 文件解析（绝对路径保留）。严格 schema 见
`schemas/job-1.0.schema.json`。

```json
{
  "schemaVersion": "1.0",
  "receptor": {"path": "receptor.pdb"},
  "ligand": {"path": "ligand.sdf"},
  "box": {
    "source": "manual",
    "center": [15.190, 53.903, 16.917],
    "size": [20.0, 20.0, 20.0]
  },
  "parameters": {"scoring": "vina", "exhaustiveness": 8, "nPoses": 9, "seed": 42},
  "reference": {"path": "reference.sdf", "rmsdThreshold": 2.0}
}
```

`box.source` 为 `manual`（必须给 center/size）或 `ligand`（按配体自动生成，
可设 `extend`）。`.pdbqt` 输入视为已准备，其他输入走 Meeko；未知字段会被拒绝。

## `result.json`

契约见 `schemas/result-1.0.schema.json`，包含：

- 软件、引擎/后端/打分版本；
- 输入路径与 SHA-256；
- 准备报告与盒子来源；
- 对接参数与相对工件路径；
- 每个姿态的亲和力、Vina RMSD、参考 RMSD 和项目六项检查；
- provenance（命令、主机、cwd、环境、git 状态）。

读取端忽略未知字段，minor 版本可加数据；结果原子写入。

## `screen.json`

筛选目前是单进程顺序执行（`--parallelism 1`），复用界面的
`screening_worker`，包括按需准备配体和逐条工件。盒子必须是 manual：
一个库没有“单个配体”可用来推导盒子。

```json
{
  "schemaVersion": "1.0",
  "receptor": {"path": "receptor.pdbqt"},
  "libraryPath": "libraries/my-library",
  "box": {
    "source": "manual",
    "center": [15.190, 53.903, 16.917],
    "size": [20.0, 20.0, 20.0]
  },
  "parameters": {"exhaustiveness": 8, "nPoses": 9, "seed": 42},
  "labelsPath": "labels.csv"
}
```

`libraryPath` 是库目录（`index.json` + `mols/`）。`entries` 可用
`{index, name, sdfPath?}` 覆盖索引。输出 `ranking.csv`、`ranking.json`、
`ligands/` 下的逐条工件；提供 `labelsPath` 时再写
`enrichment.json`/`enrichment.csv`。标签名必须与库条目标题一致。

## 互操作导出

```bash
vinastudio-cli export --result result.json \
  --format complex-pdb,pml,cxc,plip-json --out exports/
```

- `complex.pdb`：准备后的受体 + 选中姿态，配体为 `HETATM` 残基 `LIG`、链
  `L`，配体键写成 `CONECT`。
- `complex.pml` / `complex.cxc`：PyMOL 与 ChimeraX 命令文件，加载
  `complex.pdb`、显示 cartoon 并突出配体。
- `interactions.plip.json`：项目六类几何规则映射成的 **PLIP 形状** JSON，
  不是 PLIP 运行结果。没有形式电荷时盐桥仍是候选，卤键只按距离判断，
  不报告 π-堆积；文件带 `mapping`、`byType` 和 `disclaimer`。
- `--pose` 选 1-based 姿态（默认 1）；`--cutoff` 设 `plip-json` 的接触搜索
  半径（默认 4.0 Å）。

PML/CXC 引用 `complex.pdb`，因此请求任一格式都会写出该文件。不需要安装
PyMOL/ChimeraX。

## 外部引擎

适配器 = JSON manifest + 用户自备二进制；不下载、不捆绑。`engines list`
列出内置 Vina 入口，`engines doctor` 探测内置与 `--manifest` 指定的外部引擎。

```json
{
  "name": "example-engine",
  "version": "1.0",
  "license": "MIT (external)",
  "capabilities": ["dock"],
  "executable": "/opt/example/bin/dock",
  "command": ["{executable}", "--receptor", "{receptor}",
              "--ligand", "{ligand}", "--out", "{out}"],
  "output": "poses.pdbqt",
  "scoreNamespace": "example",
  "cancel": "process-kill",
  "timeout": 300
}
```

支持的占位符：`{executable}`、`{receptor}`、`{ligand}`、`{out}`、
`{center_x/y/z}`、`{size_x/y/z}`、`{scoring}`、`{exhaustiveness}`、
`{n_poses}`、`{seed}`、`{flex}`。命令不经 shell；二进制/能力缺失抛
`EngineCapabilityError`，非零退出是错误，超时会杀掉子进程。结果带 manifest
的 `scoreNamespace`，不同引擎的分数不混排。

`ExternalEngine.dock()` 可从 `vinastudio.api` 使用；`dock` 命令仍只选择内置
Vina 入口，不按任意 manifest 运行。GPL 引擎保持外部，不捆绑。

## 服务与 Docker

`vinastudio-cli server` 不启动 Qt，直接运行本地 FastAPI。未提供
`VINASTUDIO_API_TOKEN`/`--token` 时生成 token 并打印到 stderr；默认只绑定
loopback。绑定 `0.0.0.0` 时必须带 token 并显式映射端口。

无界面镜像见 `docker/Dockerfile`：

```bash
docker build -f docker/Dockerfile -t vinastudio-headless .
docker run --rm vinastudio-headless version --json
docker run --rm -p 127.0.0.1:8000:8000 \
  -e VINASTUDIO_API_TOKEN=change-me \
  vinastudio-headless server --host 0.0.0.0 --port 8000
```

挂载工作区和限制见 [docker/README.md](../docker/README.md)。

## 退出码

| 码 | 含义 |
|---:|---|
| 0 | 成功 |
| 1 | 运行失败，或验证 case 失败 |
| 2 | 输入/配置/结果非法 |
| 3 | 引擎不可用 |
| 4 | 取消 |

`validate --strict` 遇到 skipped 也返回 1。

## 1IEP 示例

```bash
uv run vinastudio-cli prepare receptor \
  -i vinastudio/resources/sample/1iep/1iep_receptorH.pdb -o /tmp/1iep-prep --json
uv run vinastudio-cli prepare ligand \
  -i vinastudio/resources/sample/1iep/1iep_ligand.sdf -o /tmp/1iep-prep --json
uv run vinastudio-cli dock --config /tmp/1iep.job.json \
  --out /tmp/1iep-out --json
uv run vinastudio-cli validate --manifest validation/manifest.json \
  --case 1iep --out /tmp/1iep-val --json
```

1IEP 预期约 −13.286 kcal/mol、对参考 RMSD 约 0.353 Å；验证命令写出
`validation-report.json` 与 `.md`。

## 边界

- CLI 不启动 HTTP，不下载数据。
- Manifest 路径相对仓库根解析，与 `scripts/validate_benchmark.py` 一致；
  外部 manifest 请用绝对路径。
- `validate` 是重对接/交叉对接 harness，不是排行榜。
- `screen` 是单进程顺序筛选，不是 HPC；不启动 HTTP。
- 富集指标需要用户提供标签集；仓库不附带数据集。
- 外部引擎不捆绑；GPL 引擎仍是外部适配器。
- `analyze` 不在首批 CLI 内；复合物 PDB、PML、CXC 与 PLIP 形状 JSON 已可用。
