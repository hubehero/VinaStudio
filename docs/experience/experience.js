(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const pointerFine = window.matchMedia('(pointer: fine)');

  const STAGES = {
    prepare: {
      title: '准备分子',
      label: '01 / PREPARE',
      body: '受体从 PDB/mmCIF 进入 Meeko 的 Polymer 路径；配体从 MOL/SDF/MOL2/SMILES 进入 RDKit 与 Meeko。两者最后都变成 PDBQT，但转换内容和失败模式并不相同。',
      path: 'core/chem/ligand_prep.py · core/chem/receptor_prep.py'
    },
    box: {
      title: '定义盒子',
      label: '02 / BOX',
      body: '盒子是 Vina 的搜索域。可以从配体、残基或口袋推导，也可以手动输入中心和尺寸。盒子内没有任何受体原子时，VinaStudio 会在启动前拒绝，而不是返回一页看似成功的 0.0 构象。',
      path: 'core/box.py · server/routers/box.py'
    },
    dock: {
      title: '运行对接',
      label: '03 / DOCK',
      body: 'Vina 在 spawn 子进程中运行，界面通过 WebSocket 接收阶段和日志。取消不是给 Vina 发命令，而是终止该 job 的所有 worker，所以按钮可以真正停下计算。',
      path: 'server/job_manager.py · core/worker.py'
    },
    review: {
      title: '复盘结果',
      label: '04 / REVIEW',
      body: '姿态、亲和力、RMSD、几何检查和相互作用放在同一份记录里；作业保留参数、输入哈希、引擎版本和种子。分数是模型估计，不是实验自由能。',
      path: 'core/chem/pose_validation.py · core/chem/ifp.py · server/results_db.py'
    }
  };

  const LAYERS = {
    desktop: {
      num: '01', title: '桌面外壳', code: 'vinastudio/desktop/', tag: 'Qt main thread',
      body: '负责窗口、原生菜单、QWebChannel 文件和目录能力，同时启动 Uvicorn 后台线程。它不实现对接算法，只负责把桌面能力接给界面。',
      items: ['允许导入 PySide6、config、logging_setup。', 'QMainWindow · 原生菜单 · QWebChannel 桥。', 'server_thread.py 启动 Uvicorn，并通过端口钩子回传实际端口。']
    },
    server: {
      num: '02', title: 'API 服务', code: 'vinastudio/server/', tag: 'local loopback',
      body: 'FastAPI 绑定回环地址，托管 SPA、REST 路由和 WebSocket。JobManager 是任务状态的唯一编排点：spawn、Pipe、取消、事件和重启恢复都在这里汇合。',
      items: ['app.py 装配应用、静态 SPA、错误映射。', 'job_manager.py 管理 spawn worker 与作业生命周期。', 'ws.py 把结构化事件广播给界面。']
    },
    core: {
      num: '03', title: '领域核心', code: 'vinastudio/core/', tag: 'no Qt / no FastAPI',
      body: '准备、对接、盒子、分析、Catalog 和导出都在这里。它只依赖科学计算库，不依赖显示器或事件循环，因此可以在测试里独立运行。',
      items: ['chem/：配体/受体准备、PDBQT、导出、相互作用、画板。', 'catalog/：SQLite Catalog、检索、迁移、种子。', 'worker.py 是唯一接触 spawn 子进程入口和 stdout 的模块。']
    },
    web: {
      num: '04', title: '界面', code: 'web/src/', tag: 'Vue 3 SPA',
      body: 'Vue 3 + 3Dmol.js 通过 HTTP 和 WebSocket 访问 Python，不直接导入任何 Python 模块。3D 视图只渲染 PDB/SDF；PDBQT 不会强行塞进 3Dmol。',
      items: ['views/：工作台、分子目录、盒子、对接、结果。', 'stores/：Pinia 状态和表单。', 'api/：HTTP、WebSocket、QWebChannel 三种边界。']
    }
  };

  const PREP = {
    ligand: {
      badge: 'ligand',
      steps: [
        ['读取与检查', 'RDKit 读入 MOL/SDF/MOL2/PDB，检查显式氢、隐式氢、3D 坐标和可旋转键。'],
        ['补氢', '<code>Chem.AddHs</code> 补真实氢；Meeko 不接受只有隐式氢的分子。'],
        ['没有 3D 时生成构象', 'ETKDG 嵌入，再用 MMFF94 优化。2D 输入不会直接进入对接。'],
        ['参数化与写出', '<code>MoleculePreparation()(mol)</code> 返回列表，取第一个 setup；<code>PDBQTWriterLegacy.write_string()</code> 返回三元组。']
      ],
      rows: [
        ['路径', 'RDKit → Meeko'], ['补氢', 'real H atoms'], ['3D', 'only if needed'],
        ['输出', 'PDBQT'], ['检查', 'rotatable bonds']
      ],
      note: 'PDBQT 只保留重原子和极性氢。原子数相比 SDF 下降是正常的，不是数据丢失；报告会告诉你补了什么、丢的是什么。'
    },
    receptor: {
      badge: 'receptor',
      steps: [
        ['读取结构', '读取 PDB 或 mmCIF；Meeko 0.8 要求残基原子连续，VinaStudio 会先归一化原子顺序。'],
        ['构建 Polymer', '使用 <code>Polymer.from_pdb_string</code>，按配置删除水分子和非聚合物基团，保留需要的辅因子/金属。'],
        ['柔性残基', '需要时可把指定侧链拆成 flexible residues，刚性与柔性部分最终一起进入 Vina。'],
        ['写出 PDBQT', '走 <code>Polymer.parameterize()</code> 和 <code>write_from_polymer()</code>，而不是配体的 writer。']
      ],
      rows: [
        ['路径', 'PDB/mmCIF → Meeko'], ['原子顺序', 'normalised'], ['水/非聚合物', 'configurable'],
        ['柔性侧链', 'optional'], ['1IEP 参考', '2702 atoms']
      ],
      note: '受体的失败通常来自模板匹配、残基定义或原子顺序，而不是“文件格式不对”一句话能概括。错误会指出具体残基。'
    }
  };

  const SCORES = {
    vina: {
      note: 'Vina 是默认路径；默认 seed 是 42，显式设为 0 才会随机。不同打分函数的能量不能直接比较。',
      engine: 'vina', size: '16.664 × 24.739 × 21.526 Å'
    },
    vinardo: {
      note: 'Vinardo 使用另一套打分和 6 个权重。它仍然通过同一个 worker 与作业模型运行，但能量不能和 Vina 直接比较。',
      engine: 'vinardo', size: '16.664 × 24.739 × 21.526 Å'
    },
    ad4: {
      note: 'AutoDock4 需要 AutoGrid4 预先算好的亲和力地图。应用不捆绑 AutoGrid4；交互式 score/optimize/randomize 会拒绝没有地图的 AD4。',
      engine: 'ad4', size: 'external maps'
    }
  };

  const LIFE = {
    request: ['提交请求', 'Vue 不等待计算完成。请求只负责创建 job，后续状态由 WebSocket 事件推进；这使取消、日志和重启恢复变得可能。'],
    spawn: ['启动 worker', 'JobManager 用 spawn 上下文创建子进程，并分配独立事件 Pipe。不能用 fork：父进程持有 Qt 和 asyncio 事件循环。'],
    compute: ['执行计算', 'worker 调 Vina/Meeko；Vina 的 stdout 重定向到作业日志，结构化事件走另一条 Pipe。'],
    stream: ['回传事件', '事件从 Pipe 到 JobManager，再进入 EventHub，经 /ws 广播给 Vue。界面只消费事件，不轮询阻塞进程。'],
    settle: ['完成或取消', '完成写 job.json 和工件；取消终止该 job 的所有 worker。重启时从持久化记录恢复历史。']
  };

  const ENTITIES = {
    files: {
      label: 'ENTITY / FILES', title: 'molecule_files',
      body: '同一个分子可以有原始结构和多个准备产物。文件是分子的附件，不是身份；路径相同也不代表分子相同。',
      rows: [['关联', 'molecule_id'], ['字段', 'kind · path · sha256'], ['身份', '不是 path']]
    },
    studies: {
      label: 'ENTITY / STUDIES', title: 'studies + study_members',
      body: 'Study 把受体、配体和辅因子放在一个研究语境里。成员带 role 和 is_primary；它不是一个简单的文件夹。',
      rows: [['成员角色', 'receptor / ligand / cofactor'], ['默认受体', 'is_primary'], ['用途', '组织一次研究']]
    },
    collections: {
      label: 'ENTITY / COLLECTIONS', title: 'collections + collection_members',
      body: '集合是可嵌套的组织树，用来按课题、项目或习惯分类；它不替代 Study，也不携带受体/配体角色。',
      rows: [['结构', 'parent_id 自嵌套'], ['成员', 'collection_members'], ['语义', '组织，不是实验']]
    },
    libraries: {
      label: 'ENTITY / LIBRARIES', title: 'libraries + library_members',
      body: '筛选库是虚拟筛选的输入集合。成员引用 Catalog 分子并带 entry_index；运行时物化到现有的 libraries/<id>/mols 目录。',
      rows: [['成员', 'library_members'], ['顺序', 'entry_index'], ['用途', '批量 / 筛选输入']]
    }
  };

  const PALETTE = [
    { title: '模型的边界', sub: '01 / the model', href: '#model', keys: 'vina 分数 自由能 准备 pdbqt' },
    { title: '运行结构', sub: '02 / architecture', href: '#architecture', keys: 'qt fastapi spawn 进程 线程 架构' },
    { title: '准备实验室', sub: '03 / preparation', href: '#prepare', keys: '配体 受体 meeko rdkit 补氢 3d' },
    { title: '对接控制台', sub: '04 / docking', href: '#docking', keys: 'vina vinardo ad4 参数 盒子 seed exhaustiveness' },
    { title: '任务生命周期', sub: '05 / lifecycle', href: '#lifecycle', keys: 'job websocket cancel pipe spawn' },
    { title: 'Catalog 图谱', sub: '06 / catalog', href: '#catalog', keys: 'molecule study collection library identity' },
    { title: '验证与边界', sub: '07 / validation', href: '#validation', keys: '1iep posebusters rmsd 60/60 置信区间' },
    { title: '限制与文档', sub: '08 / boundaries', href: '#limits', keys: 'ad4 地图 progress pdbqt 限制 文档' },
    { title: '结构图谱 HTML', sub: 'tree map', href: '../structure.html', keys: '结构 目录 树 html' },
    { title: '架构文档', sub: 'document', href: '../ARCHITECTURE.zh-CN.md', keys: 'architecture 约束 设计' },
    { title: '学术验证', sub: 'document', href: '../ACADEMIC_VALIDATION.zh-CN.md', keys: 'validation 证据 论文 参考' }
  ];

  // ── Pipeline stage explorer ────────────────────────────────
  const flowDetail = $('#flowDetail');
  const stageButtons = $$('[data-stage]');
  function setStage(key) {
    const data = STAGES[key];
    if (!data) return;
    stageButtons.forEach((button) => {
      const active = button.dataset.stage === key;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', String(active));
    });
    flowDetail.innerHTML = `
      <div class="flow-detail-top"><h3>${data.title}</h3><span class="pill teal">${data.label}</span></div>
      <p>${data.body}</p><span class="path">${data.path}</span>`;
  }
  stageButtons.forEach((button) => button.addEventListener('click', () => setStage(button.dataset.stage)));

  // ── Architecture layer explorer ────────────────────────────
  const layerDetail = $('#layerDetail');
  const layerButtons = $$('[data-layer]');
  function setLayer(key) {
    const data = LAYERS[key];
    if (!data) return;
    layerButtons.forEach((button) => {
      const active = button.dataset.layer === key;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    layerDetail.innerHTML = `
      <div class="layer-detail-top">
        <div><p class="mono-label">LAYER / ${data.num}</p><h3>${data.title}</h3><div class="layer-code">${data.code}</div></div>
        <span class="pill teal">${data.tag}</span>
      </div>
      <p>${data.body}</p>
      <ul>${data.items.map((item) => `<li>${item}</li>`).join('')}</ul>`;
  }
  layerButtons.forEach((button) => button.addEventListener('click', () => setLayer(button.dataset.layer)));

  // ── Preparation lab ────────────────────────────────────────
  const prepSteps = $('#prepSteps');
  const prepReport = $('#prepReport');
  const prepBadge = $('#prepBadge');
  const prepButtons = $$('[data-prep]');
  function setPrep(key) {
    const data = PREP[key];
    if (!data) return;
    prepButtons.forEach((button) => {
      const active = button.dataset.prep === key;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', String(active));
    });
    prepBadge.textContent = data.badge;
    prepSteps.innerHTML = data.steps.map(([title, body], index) => `
      <li class="prep-step"><span class="prep-step-index">0${index + 1}</span><div><h4>${title}</h4><p>${body}</p></div></li>`).join('');
    prepReport.innerHTML = data.rows.map(([label, value]) => `<div class="report-row"><span>${label}</span><b>${value}</b></div>`).join('');
    const note = prepReport.parentElement.querySelector('.note');
    if (note) note.textContent = data.note;
  }
  prepButtons.forEach((button) => button.addEventListener('click', () => setPrep(button.dataset.prep)));

  // ── Docking protocol builder ───────────────────────────────
  const coordinates = '15.190, 53.903, 16.917';
  const exhaustiveness = $('#exhaustiveness');
  const poses = $('#poses');
  const seed = $('#seed');
  const exhValue = $('#exhValue');
  const posesValue = $('#posesValue');
  const protocolPreview = $('#protocolPreview');
  const scoreNote = $('#scoreNote');
  const scoreButtons = $$('[data-score]');
  let selectedScore = 'vina';

  function protocolText() {
    return [
      `engine       : ${SCORES[selectedScore].engine}`,
      `exhaustiveness: ${exhaustiveness.value}`,
      `poses         : ${poses.value}`,
      `seed          : ${seed.value || '0'}`,
      `box           : ${coordinates}`,
      `size          : ${SCORES[selectedScore].size}`,
      'note          : resumable local job'
    ].join('\n');
  }
  function updateProtocol() {
    exhValue.textContent = exhaustiveness.value;
    posesValue.textContent = poses.value;
    protocolPreview.textContent = protocolText();
  }
  function setScore(key) {
    selectedScore = key;
    scoreButtons.forEach((button) => {
      const active = button.dataset.score === key;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    scoreNote.textContent = SCORES[key].note;
    updateProtocol();
  }
  scoreButtons.forEach((button) => button.addEventListener('click', () => setScore(button.dataset.score)));
  [exhaustiveness, poses, seed].forEach((input) => input.addEventListener('input', updateProtocol));

  const copyProtocol = $('#copyProtocol');
  const copyStatus = $('#copyStatus');
  async function copyText(text) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const area = document.createElement('textarea');
        area.value = text;
        area.style.position = 'fixed';
        area.style.opacity = '0';
        document.body.appendChild(area);
        area.select();
        document.execCommand('copy');
        area.remove();
      }
      copyStatus.textContent = 'copied';
    } catch {
      copyStatus.textContent = 'select manually';
    }
    window.setTimeout(() => { copyStatus.textContent = 'ready'; }, 1800);
  }
  copyProtocol.addEventListener('click', () => copyText(protocolPreview.textContent));

  // ── Lifecycle timeline ─────────────────────────────────────
  const timelineSteps = $$('[data-life]');
  const lifeTitle = $('#lifeTitle');
  const lifeBody = $('#lifeBody');
  const playButton = $('#playLifecycle');
  let lifeIndex = 0;
  let lifeTimer = 0;

  function setLife(key) {
    const data = LIFE[key];
    if (!data) return;
    timelineSteps.forEach((step, index) => {
      const active = step.dataset.life === key;
      step.classList.toggle('is-active', active);
      if (active) lifeIndex = index;
    });
    lifeTitle.textContent = data[0];
    lifeBody.textContent = data[1];
  }
  timelineSteps.forEach((step) => step.addEventListener('click', () => {
    window.clearInterval(lifeTimer);
    lifeTimer = 0;
    playButton.textContent = '播放路径';
    setLife(step.dataset.life);
  }));
  playButton.addEventListener('click', () => {
    window.clearInterval(lifeTimer);
    lifeIndex = 0;
    setLife(timelineSteps[0].dataset.life);
    playButton.textContent = '播放中…';
    lifeTimer = window.setInterval(() => {
      lifeIndex += 1;
      if (lifeIndex >= timelineSteps.length) {
        window.clearInterval(lifeTimer);
        lifeTimer = 0;
        playButton.textContent = '播放路径';
        return;
      }
      setLife(timelineSteps[lifeIndex].dataset.life);
    }, 1150);
  });

  // ── Catalog entity explorer ────────────────────────────────
  const entityTitle = $('#entityTitle');
  const entityBody = $('#entityBody');
  const entityRows = $('#entityRows');
  const entityLabel = $('.entity-detail .mono-label');
  const entityButtons = $$('[data-entity]');
  function setEntity(key) {
    const data = ENTITIES[key];
    if (!data) return;
    entityButtons.forEach((button) => {
      const active = button.dataset.entity === key;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    entityLabel.textContent = data.label;
    entityTitle.textContent = data.title;
    entityBody.textContent = data.body;
    entityRows.innerHTML = data.rows.map(([label, value]) => `<div class="report-row"><span>${label}</span><b>${value}</b></div>`).join('');
  }
  entityButtons.forEach((button) => button.addEventListener('click', () => setEntity(button.dataset.entity)));


  function scrollToHash(hash) {
    const section = document.querySelector(hash);
    if (!section) return;
    if (hash === '#top') {
      window.scrollTo({ top: 0, behavior: prefersReduced.matches ? 'auto' : 'smooth' });
      return;
    }
    const head = section.querySelector('.section-head');
    const top = (head || section).getBoundingClientRect().top + window.scrollY - 84;
    window.scrollTo({ top: Math.max(0, top), behavior: prefersReduced.matches ? 'auto' : 'smooth' });
  }

  document.addEventListener('click', (event) => {
    const link = event.target.closest('a[href^="#"]');
    if (!link) return;
    const hash = link.getAttribute('href');
    if (!hash || !document.querySelector(hash)) return;
    event.preventDefault();
    history.pushState(null, '', hash);
    scrollToHash(hash);
  });

  // ── Command palette ───────────────────────────────────────
  const palette = $('#palette');
  const paletteInput = $('#paletteInput');
  const paletteResults = $('#paletteResults');
  let filtered = PALETTE;
  let activeResult = 0;
  let returnFocus = null;

  function renderPalette(query = '') {
    const q = query.trim().toLowerCase();
    filtered = PALETTE.filter((item) => `${item.title} ${item.sub} ${item.keys}`.toLowerCase().includes(q));
    activeResult = 0;
    if (!filtered.length) {
      paletteResults.innerHTML = '<li class="palette-empty">没有匹配的章节或概念。</li>';
      return;
    }
    paletteResults.innerHTML = filtered.map((item, index) => `
      <li class="palette-result${index === 0 ? ' is-active' : ''}" role="option" aria-selected="${index === 0}" data-index="${index}">
        <span class="result-num">${String(index + 1).padStart(2, '0')}</span>
        <span>${item.title}</span><small>${item.sub}</small>
      </li>`).join('');
  }
  function openPalette() {
    returnFocus = document.activeElement;
    palette.hidden = false;
    document.body.style.overflow = 'hidden';
    paletteInput.value = '';
    renderPalette('');
    window.setTimeout(() => paletteInput.focus(), 30);
  }
  function closePalette() {
    palette.hidden = true;
    document.body.style.overflow = '';
    if (returnFocus) returnFocus.focus();
  }
  function pickPalette(index) {
    const item = filtered[index];
    if (!item) return;
    if (item.href.startsWith('#')) {
      closePalette();
      history.pushState(null, '', item.href);
      scrollToHash(item.href);
    } else {
      window.location.href = item.href;
    }
  }
  paletteInput.addEventListener('input', () => renderPalette(paletteInput.value));
  paletteResults.addEventListener('click', (event) => {
    const result = event.target.closest('[data-index]');
    if (result) pickPalette(Number(result.dataset.index));
  });
  palette.addEventListener('click', (event) => { if (event.target === palette) closePalette(); });
  $$('[data-palette]').forEach((button) => button.addEventListener('click', openPalette));
  window.addEventListener('keydown', (event) => {
    const key = event.key.toLowerCase();
    if ((event.metaKey || event.ctrlKey) && key === 'k') {
      event.preventDefault();
      palette.hidden ? openPalette() : closePalette();
      return;
    }
    if (!palette.hidden) {
      if (event.key === 'Escape') { event.preventDefault(); closePalette(); }
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        if (!filtered.length) return;
        activeResult = (activeResult + (event.key === 'ArrowDown' ? 1 : -1) + filtered.length) % filtered.length;
        $$('.palette-result', paletteResults).forEach((item, index) => {
          item.classList.toggle('is-active', index === activeResult);
          item.setAttribute('aria-selected', String(index === activeResult));
        });
      }
      if (event.key === 'Enter') { event.preventDefault(); pickPalette(activeResult); }
      return;
    }
    if (event.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
      event.preventDefault();
      openPalette();
    }
  });

  // ── Mobile menu / calm mode ───────────────────────────────
  const menuButton = $('[data-menu]');
  const mobileNav = $('#mobileNav');
  menuButton.addEventListener('click', () => {
    const open = document.body.classList.toggle('menu-open');
    menuButton.setAttribute('aria-expanded', String(open));
  });
  mobileNav.addEventListener('click', (event) => {
    if (event.target.closest('a')) {
      document.body.classList.remove('menu-open');
      menuButton.setAttribute('aria-expanded', 'false');
    }
  });

  const calmButton = $('[data-calm]');
  const calmLabel = $('[data-calm-label]');
  let calm = false;
  calmButton.addEventListener('click', () => {
    calm = !calm;
    document.body.classList.toggle('calm', calm);
    calmButton.setAttribute('aria-pressed', String(calm));
    calmLabel.textContent = calm ? '动效' : '静默';
    drawField();
  });

  // ── Reading progress, active rail, reveal ─────────────────
  const progress = $('#progress');
  const railLinks = $$('.rail-link');
  const sections = $$('main section[id]');
  function updateProgress() {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    progress.style.width = `${max > 0 ? Math.min(100, (window.scrollY / max) * 100) : 0}%`;
  }
  window.addEventListener('scroll', updateProgress, { passive: true });
  updateProgress();

  const sectionObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const id = entry.target.id;
      railLinks.forEach((link) => link.classList.toggle('is-active', link.getAttribute('href') === `#${id}`));
    });
  }, { rootMargin: '-24% 0px -62% 0px', threshold: 0 });
  sections.forEach((section) => sectionObserver.observe(section));

  const revealObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      if (entry.target.id === 'ciCard') entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: .12 });
  $$('.reveal, .stagger').forEach((element) => revealObserver.observe(element));

  // ── Card pointer spotlight ────────────────────────────────
  if (pointerFine.matches) {
    $$('.card').forEach((card) => {
      card.addEventListener('pointermove', (event) => {
        const rect = card.getBoundingClientRect();
        card.style.setProperty('--mx', `${event.clientX - rect.left}px`);
        card.style.setProperty('--my', `${event.clientY - rect.top}px`);
      });
    });
  }

  // ── Ambient field canvas ──────────────────────────────────
  const canvas = $('#field');
  const ctx = canvas.getContext('2d');
  let points = [];
  let fieldFrame = 0;
  let fieldWidth = 0;
  let fieldHeight = 0;

  function resizeField() {
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    fieldWidth = rect.width;
    fieldHeight = rect.height;
    canvas.width = Math.max(1, Math.floor(fieldWidth * dpr));
    canvas.height = Math.max(1, Math.floor(fieldHeight * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const count = Math.max(24, Math.min(52, Math.floor(fieldWidth / 26)));
    points = Array.from({ length: count }, (_, i) => ({
      x: Math.random() * fieldWidth,
      y: Math.random() * fieldHeight,
      vx: (Math.random() - .5) * .18,
      vy: (Math.random() - .5) * .18,
      r: i % 7 === 0 ? 1.8 : 1.1,
      tone: i % 5 === 0 ? 'violet' : 'teal'
    }));
    drawField();
  }

  function drawField(animate = false) {
    if (!ctx || !fieldWidth || !fieldHeight) return;
    window.cancelAnimationFrame(fieldFrame);
    ctx.clearRect(0, 0, fieldWidth, fieldHeight);
    const still = prefersReduced.matches || calm;
    points.forEach((point, index) => {
      if (!still) {
        point.x += point.vx;
        point.y += point.vy;
        if (point.x < 0 || point.x > fieldWidth) point.vx *= -1;
        if (point.y < 0 || point.y > fieldHeight) point.vy *= -1;
      }
      for (let next = index + 1; next < points.length; next += 1) {
        const other = points[next];
        const dx = point.x - other.x;
        const dy = point.y - other.y;
        const distance = Math.hypot(dx, dy);
        if (distance < 120) {
          ctx.beginPath();
          ctx.moveTo(point.x, point.y);
          ctx.lineTo(other.x, other.y);
          ctx.strokeStyle = `rgba(100, 230, 210, ${(.11 * (1 - distance / 120)).toFixed(3)})`;
          ctx.lineWidth = .6;
          ctx.stroke();
        }
      }
      ctx.beginPath();
      ctx.arc(point.x, point.y, point.r, 0, Math.PI * 2);
      ctx.fillStyle = point.tone === 'violet' ? 'rgba(147, 132, 255, .62)' : 'rgba(100, 230, 210, .58)';
      ctx.fill();
    });
    if (!still) fieldFrame = window.requestAnimationFrame(() => drawField(true));
  }

  resizeField();
  window.addEventListener('resize', resizeField);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) window.cancelAnimationFrame(fieldFrame);
    else drawField();
  });
  prefersReduced.addEventListener?.('change', () => drawField());

  // ── Initial state ─────────────────────────────────────────
  setStage('prepare');
  setLayer('desktop');
  setPrep('ligand');
  setScore('vina');
  setLife('request');
  setEntity('files');
  updateProtocol();
  renderPalette('');
  if (window.location.hash) window.setTimeout(() => scrollToHash(window.location.hash), 60);
})();
