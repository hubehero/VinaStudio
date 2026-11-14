# 分子目录（Catalog）

> 状态：在 `feat/molecule-catalog-v2` 分支开发中。

分子管理正在升级为工作区级 **Catalog**，数据保存在
`<workspace>/catalog.sqlite`。结构文件仍在磁盘上；数据库保存身份、元数据、
关系和筛选库成员。

## 概念

| 概念 | 含义 |
|---|---|
| 分子 | 一个化学/结构身份，可关联多个来源文件与准备产物 |
| Study | 生物学上下文：1 个或多个受体 + 相关配体 |
| 集合 | 可嵌套的组织目录，与 Study 独立 |
| 筛选库 | 有序的 Catalog 分子集合，供批量/虚拟筛选使用 |
| 标签 | 多对多标签，可与集合并存 |

受体/配体是 **Study 成员的角色**，不是分子的固有属性；同一结构可以在不同
Study 中承担不同角色。

## 工作流

1. 导入 SDF/MOL2/PDB/PDBQT/mmCIF、SMILES、2D 画板、内置示例，或从 RCSB /
   PubChem / ChEMBL 获取结构。
2. 计算身份：配体用完整 InChIKey（另存 parent key），受体用 PDB ID 或内容
   哈希。相同身份合并文件与来源。
3. 从选中的受体/配体创建 Study，或接受基于 PDB 文件名/来源前缀的自动配对
   建议。
4. 用集合与标签组织；使用自由文本或字段语法检索。
5. 需要时准备受体/配体 PDBQT。
6. 从选中配体、集合或检索结果创建 **筛选库**，也可在选择器中把筛选结果
   直接保存为库。
7. 批量对接与虚拟筛选使用冻结的 **本次运行选择**：直接读取源文件，按配体
   惰性准备 PDBQT；`libraries/<id>/mols` 仅保留给旧库与导出，不再是每次
   运行前必须复制的目录。

## 内置本科药物库

内置药物 SDF 使用 CoordGen 与规范 2D 朝向；旧工作区会一次性刷新缓存图形，但不会重建已删除的库。详情预览请求 `/preview3d`，源文件为 2D 时会生成并缓存 ETKDG 构象；这是算法构象，不代表实验构象。

首次访问工作区时会播种一套带版本的本科教学库，包含 125 个常用药物
（中英文名、类别、PubChem CID、InChIKey）。生成的是普通 Catalog 分子、
集合和筛选库；删除后下次启动不会自动回灌。播种源文件是 2D SDF，对接前
仍需正常准备 3D/PDBQT。范围、书目依据和科学边界见
[BUILTIN_LIBRARY.zh-CN.md](BUILTIN_LIBRARY.zh-CN.md)。首次访问还会播种
[BUILTIN_RECEPTORS.zh-CN.md](BUILTIN_RECEPTORS.zh-CN.md)：27 个 RCSB PDB
药物靶点结构，作为受体分子放入按类别嵌套的集合（不是筛选库）。

## 检索与选择

示例：

```text
imatinib
tag:kinase
source:chembl
study:"1IEP study"
collection:"Kinase leads"
kind:ligand
mw:300-600
qed:>=0.5
tpsa:<=140
logp:<=5
rotatable:<=10
```

检索在服务端用 SQLite FTS5 与结构化索引完成，前端不再全量过滤。中文 2 字
查询回退到有界的子串搜索。导入时保存 MW/QED/Lipinski/TPSA/LogP/HBD/HBA/
可旋转键等描述符。

Batch 与 Screening 共用 Catalog 选择器：支持 All/Study/集合/筛选库/未归类
scope、搜索、描述符范围、仅已准备、分页和全选匹配。大结果由服务端解析成
**本次运行选择**（最多 5 万），不再传巨型 ID 数组；可复用集合仍保存为
Library。

## 身份与去重

- 配体主身份为完整 InChIKey。
- `parent_inchi_key` 只用于“可能重复”建议；盐型、立体异构体、互变异构体
  不会被静默合并。
- 重复导入同一身份会追加文件/来源/别名，不新建分子。
- 受体优先取文件名中的 PDB ID，否则用内容哈希。

## 迁移

首次访问 Catalog 时一次性导入旧 `molecules.json` 与
`libraries/*/index.json`；原文件备份为 `molecules.json.pre-catalog`，不删除。
迁移幂等，不删除用户文件。

## 运行快照与库失效

运行选择是不可变快照：保存原始 `memberCount` 与每个成员的 identity。删除分子会把
所有受影响的运行选择标记为 `stale`（`invalidatedAt`、`invalidReason:
member_deleted`），批量/虚拟筛选在重建选择前拒绝启动。API 返回
`liveMemberCount` 和 `stale`，界面显示原因，而不是静默减少运行分子。

Catalog 的库成员关系是权威数据。增删成员、准备成员或删除其分子，都会使派生的
`libraries/<id>/` 物化目录失效；旧的 legacy 库视图必须重新物化，不能继续显示旧
成员或过期的 `prepared_path`。


## 已知边界

- 新页面提供受体/配体准备选项对话框，并已接入基于序列的柔性残基选择器。
- Study/集合/筛选库有当前 Scope 管理头，支持重命名、移除成员、删除、
  集合成员管理和多受体 Study 的主受体切换。
- 支持保存检索、来源/标签/状态 facet、排序、页大小、全选筛选结果和列显示配置；表格使用 `ElTableV2` 虚拟渲染行，服务器仍按页返回，后续页通过分页访问。
- Batch 与虚拟筛选可从冻结的选择 id 启动；Catalog 库从源路径读取，只准备
  被选中的分子，未准备/失败都有明细。
- 虚拟筛选在库、运行和历史中显示库的显示名，同时请求仍使用稳定目录 id；点击排名行可查看单配体结果（评分、SMILES、耗时和输出目录）。
- 选择器不建立本地指纹/ANN 索引，也不提供子结构/相似性搜索；那仍是独立的
  产品决策。
- 1iep Catalog 已实测准备 → Study → 对接 → Catalog 库虚拟筛选；Catalog 中单独
  准备的分子也会在启动和准备完成后进入旧对接选择器，不要求先建 Study。

## 源路径与预览边界

桌面端原生文件选择器可以返回工作区外的绝对路径。这是用户显式选择，不是
preview 接受任意路径：Catalog 把这类文件记录为 `path_kind: external`，
`/molecules/{id}/preview` 只读取该分子已经登记的文件，不接受裸路径参数。
浏览器导入必须走 `/api/files/upload`，由服务端写入工作区。回环 API 还会拒绝
带有外部 `Origin` 的状态修改请求，规则见 `docs/ARCHITECTURE.md`。
外部源文件保留在原位置以支持原地工作流；需要
跨机器可移植时，应把文件复制到工作区。



- **准备库**在进入时校验 PDBQT 是否存在；产物缺失的分子会退回未准备，而不是
  留下失效条目。取消准备会返回实际释放/保留的缓存字节，并保留仍被引用的缓存。
  它是只读动态作用域（`prep=prepared`），只列出已有准备产物的受体和配体；源文件
  保留，该库不能手动扩充或重命名。

## 面向开发者

- 核心：`vinastudio/core/catalog/`（`db`、`store`、`query`、`identity`、`migrate`、`suggest`、`library`）
- API：`vinastudio/server/routers/catalog.py`
- UI：`web/src/components/panels/catalog/MoleculeCatalogView.vue`
- 契约类型：`web/src/types/api.ts`
- 迁移是单向的；不要再为 `molecules.json` 引入第二条写入路径。
