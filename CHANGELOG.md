# Changelog

所有显著变更记录于此。格式参照 Keep a Changelog，版本遵循 SemVer。

## [0.13.0] - 2026-11-05

### Added（工作台分区改版·第一期：A 连载管理台 + D 项目文件树）
- **连载管理台 `/app/serial`**（新页，三栏管理壳——单章/连载分家第一步，
  双入口过渡：create 暂不动）：
  - **左栏·约束口**：规范层档案入口 + **项目文件树**（见下）；
  - **中栏·本章工作流**：装配→G0 表单→立意→拍子→生成→交付（与单章页
    **同源复用**，见 creation.js）；
  - **右栏·运行态**：预算·本章钱包 + 记忆·隔离区 + **本章总结卡**（新：
    交付后 digest/状态变更/伏笔埋设显性化——数据全部来自现有 propose_delta
    零新提取，人扫一眼再合并的质量控制点）；
  - 顶部工具条：开新弧/漂移网/交接汇总/量产连跑/看板跳转（长篇机制收拢）；
    首开流程引导一行（开弧→图纸确认→探针→连跑→弧末）。
- **项目文件树**（左栏常驻，设想 §五 五档）：
  - 只读树 + 来源标注（交付落盘/规范层档案/成本账本/归档/方案槽…）+
    运行态文件灰标（sessions/slots 不入库）；
  - 预览（20k 字符截断，二进制识别）+ 单文件下载；
  - **复用既有执法端点**：章节改名（章号保留/消毒/409）/删除（.trash 软删）
    ——零新增写入通道；
  - **资源管理器逃生门**（win: os.startfile / mac: open / linux: xdg-open，
    可 patch）——文件协议红线"用户可带走"的一键化；
  - 全 path 参数 traversal guard（resolve+parent 校验）。
- **共享 creation.js**：创作流程 JS 从 create.html 抽出为 `/static/creation.js`
  ——单章页与连载台**同一份逻辑**（双入口同源，杜绝双份维护）；onboarding
  按缺元素优雅跳过；create 页行为零变化（回归测试改断外链）。

### 测试
- 新增 test_serial_page_and_tree（页面关键件/共享脚本可达且 create 零内联/
  树来源标注/预览截断/traversal 拦截/下载/资源管理器 patch 调用）；回归
  test_create_page_sidebar 改断外链；**测试 181+9**

## [0.12.1] - 2026-11-05

### Added（v0.12 欠账补完，设想 §5.2/§七/§九 清单收口）
- **专名总账门**（names_check.py 三模态合并，家法：灾厄前线 names_check.sh
  弧二实战验证后移植）：
  - ② **禁用变体**（新）：`--variants bible/专名表.tsv`（正名<TAB>禁用变体
    1|变体2）——形近/音近错写由作者养表，不做自动 NER（边界留档）；
  - ③ **人物状态门**（新，J8 判定代理）：卡面「状态：死亡（第N章）/离场
    （第N章）」→ 死亡/离场者正名或别名出现于**引号外叙述**（“”内对话=
    提及豁免）→ 停等人裁决；
  - ④ **卡面禁语**（§5.2 人物·言行，黄级）：卡面「禁语：词1|词2」同现 →
    记录供人扫，不默认红停；
  - ① 出场统计+零出现（原有契约不动，语料级）——**修复潜伏 bug：names.json
    字典壳格式（{"names": [...]}）此前从未被支持**，测试锁死；
  - 接线：长篇项目每稿门禁+交付检查自动带 `--variants/--characters`；
    连跑红即停升级（[专名错写]/[状态冲突]=红停，[禁语·黄]=黄灯）；
  - 模板：新建项目自动生成 `bible/专名表.tsv` + characters.md 状态/禁语行
- **批后趋势报告**（设想 §七 批后治理）：POST /longform/batch/report =
  fp_check `--per-file` 对本批各章跑指纹偏差曲线，归档 `整合/趋势报告/`
  （永不覆盖）；连跑面板加按钮

### 测试
- 新增 test_names_check_and_trend（变体/状态门/引号豁免/禁语黄级/零出现
  向后兼容/交付带 names_check/趋势归档/轻量 400）；**测试 180+9**

## [0.12.0] - 2026-11-05

### Added
- **量产连跑**（设计：工作台v0.12-量产连跑-设计设想.md，决策点 J1-J9 按推荐
  落地；定位：量大且章章同质的灌水段专用工具，非长篇默认路径）：
  - **章计划表规划器**（GET /longform/batch/plan，0 token）：M 份 G0 简报
    自动产出——弧块锚点/弧位计算/记忆摘要/未回收伏笔/前章真实结尾钩子接
    批内首章；关键词派生（核心人物名+锚点专名，J6）；**关键章自动摘出**
    （弧末章/有未回收伏笔 → 默认关键章，J4）；**探针章不进连跑**（每弧前
    2 章，J9）；预检数据：成本预估（近 5 章中位数×N）/量产路由检查/
    弧末自动截断（不跨弧末）/批量硬顶 10（J2）
  - **前端连跑循环**（J1：人在场原则，关页面即停、已交付章零损失）：
    每章 = 冻结简报 → 立意（自动取推荐）→ 拍子 → 单发生成 → **红即停清单**
    （门禁红/重试触顶仍截断/表外设定级数字/字数越界 2200–150%/digest 异常/
    中高风险记忆 delta）→ 交付 → digest 校验 + **低风险自动合并** →
    预算三态（**预警=暂停等人在场确认**，halt=终止）→ 黄灯连击 ×3 停（J3）
    ——无自动修订（铁律），每站日志可见，断点=最后交付章
  - **服务端既有执法全程在环**：拆账强制/预算止损闸/数字对照门照常 429/409
  - 计划表 UI：逐行可编辑（题/衔接/结尾钩子/关键词/类型），钩子链自动接续，
    一次预审 N 章代替每章审一次（§3.3）

### 优化
- 账本行新增 `session` 字段（append_cost）：预算 spend 排除本会话行——
  修复交付后 spend 双算会提前误触闸；/save 响应携带交付后预算三态

### 测试
- 新增 test_longform_batch_plan（边界校验/探针/钩子链/弧末截断/关键章标记/
  交付带预算态/session 字段/轻量拒绝）；**测试 179+9**

## [0.11.3] - 2026-11-05

### Added
- **长篇模式·阶段 D：弧末治理与交接**（v0.11 收官；来源：灾厄前线工单一
  G3 清单模式 + 两次实战交接汇总 + 图纸门 §5.3 防线4）：
  - **弧末一键漂移网**：GET /longform/arcanet 生成清单模式审查指令包
    （复制到**独立会话/子代理**执行）——只验硬数字表逐条 + 伏笔动作 +
    弧节拍落位，数字类错误强制标注三分诊断来源（表外自造/表内执行错/
    表本身错）；审查完成 POST /longform/arcanet/archive 归档至
    `整合/一致性报告/弧N-漂移网-*.md`（永不覆盖，撞名加序号）
  - **一键交接汇总**：GET /longform/handover 从进度（现役章/字数/弧状态/
    漂移网归档态）/成本（交付口径累计）/断点（最近摘要+上章 G0 结尾钩子）/
    未回收伏笔/待办（图纸变更未确认、写完未归档的弧）自动生成草稿；
    POST /longform/handover/save 落盘项目根 `00_交接汇总-草稿-*.md`
    （**永不覆盖用户手写版**）
  - **图纸变更 hash 检测**（§5.3 防线4）：outline.md + bible/* 的 sha256
    基线存 `style/blueprint.json`——外部直改文件也会被检测（开弧/图纸确认
    为人工基线时刻）；G0 面板亮"⚠ 图纸变更未确认"banner + **账本回扫**一键
    （POST /longform/retroscan = numbers_check --all 全量对照历史章）+
    "重新确认图纸"重置基线（POST /longform/blueprint_confirm）
- 创作页长篇工具条：开新弧旁新增「弧末漂移网」「交接汇总」按钮 + 弧末工具面板

### 优化
- 交付记录 tool → web-create v0.11.3；交接草稿自动列出"写完但漂移网未归档"
  的弧（弧末治理闭环提醒）

### 测试
- 新增 test_longform_arcanet_handover_blueprint（指令包要素/三分诊断/归档
  撞名不覆盖/交接含进度钩子弧态/外部改图纸→变更旗→回扫→再确认清除/
  轻量项目全拒绝）；**测试 178+9**

## [0.11.2] - 2026-11-05

### Added
- **长篇模式·阶段 C：成本框架**（设计：工作台v0.11-C成本控制-设计设想.md
  §四"三层钱包+两道闸"；定律：成本=轮数×上下文重发）：
  - **预算层**（C4 文件协议）：`style/budget.json`——单章预算（默认 15 万
    tokens）/ 弧预算（默认 150 万）/ 止损倍数（默认 ×2），长篇骨架自动生成；
    默认值标注"待标定"（C1/D7：medium 档实验落地后校准）
  - **预算配置端点**：GET/POST /longform/budget，rev 乐观锁先行
    （死规矩 #10：网页与手改双写入方）——调高预算 = halt 三出路之一
  - **预警闸（软）**：本章累计 ≥ 单章预算 → 生成/修订前 confirm"本章已烧
    X / 预算 Y"（把冲动消费隔一道）；响应带预算三态
  - **止损闸（硬）**：本章累计 ≥ 预算×倍数 → 服务端 429（生成/修订全拦，
    显式 allow_over_budget 可越，G4 最高指令权永不真锁死）；前端锁按钮 +
    诊断面板（生成/修订/其他分桶 + 账本历史）+ 三出路（换模型/调高预算/
    放弃本章）
  - **拆账强制**（C 执法）：开"最新章+1"前，上一章必须有 cost.jsonl 交付
    拆账记录，409 拦截（显式确认可越过）——账本从"可选看"变"必经之路"；
    改写旧章不受限
  - **记账分桶**：session 总账拆 gen/rev/other（halt 诊断"哪一环节烧的"）；
    本章消耗 = 会话分桶 + 账本本章历史行（弃稿重开场景，C5 估算口径照记）
  - **量产路由**（C3/C4 决策）：路由表新增 `write_mass`（配置页可选行）；
    G0 表单加"章类型"（量产=默认/关键），量产章的立意/拍子/生成走
    write_mass（未配置自动回退 write），关键章与修订始终走 write
  - **看板**（C5/历史页升格）：长篇项目显示弧聚合视图——弧预算占用进度条 +
    预算三态徽章 + 每章拆账条形（GET /history/board，与 cost.jsonl 同源）

### 优化
- 预算状态随每次生成/修订响应返回（调用前执法、调用后重算展示）
- 交付记录 tool → web-create v0.11.2

### 测试
- 新增 test_longform_budget_config_and_ledger_gate（乐观锁/拆账 409/越过/
  补账放行/轻量 400）+ test_longform_budget_states_and_write_mass（预警→
  止损 429→显式解锁 e2e、分桶断言、量产/关键路由 model 断言、看板聚合）；
  **测试 177+9**

## [0.11.1] - 2026-11-05

### Added
- **长篇模式·阶段 B：G0 写前简报 + 硬数字表进装配 + 数字对照门**
  （治理来源：灾厄前线 G0"缺一不派发"七字段；图纸门 §5.3 与数字门三分类
  §5.1 见 项目管理/计划书/工作台v0.12-量产连跑-设计设想.md）：
  - **G0 写前表单**（长篇项目）：装配预览后出现七字段面板
    （原作锚点/主角状态/弧线位置/伏笔动作/出场口癖/结尾钩子/衔接），
    自动预填自弧块/记忆 recap/上一章 G0 结尾钩子，可改；
    缺字段生成按钮置灰 + "跳过 G0"链接（D4：留痕于交付记录）
  - **弧简报卡（G-0.5 图纸门）**：写本章前过目本弧四字段+硬数字口径；
    "确认图纸"落痕 outline.md 弧块（`- 图纸确认：日期`），未确认的弧
    不解锁生成——灾厄前线 25 万字事故（大纲细微误差被逐章忠实执行）的
    弧前防线
  - **探针章**（J9）：每弧前 2 章标记 🎯，交付时要求显式验收确认——
    结构性误差最便宜的修正时刻是只写了 1-2 章的时候
  - **硬数字表当前弧节进装配**（规范层附件，不参与预算裁剪）：
    覆盖当前章号的 `## 弧N《…》（第X-Y章）` 节自动注入，
    注明"唯一口径：只准引用，不得自造"
  - **数字对照门 numbers_check.py**（advisory 报不拦，CLI 等价）：
    表内口径须同值/约略词（约39/39余）/"一万两千多"式取整（±20%）合规；
    表外数字分级（≥100 设定级候选/<100 场景级）；`## 豁免数字` 节豁免；
    中文数字（三千五百/一万二/二十五/三千五百零六）与阿拉伯数字双解析；
    `--all` 全量回扫模式（retroscan：新账落定后重扫历史章）
  - 生成/流式每稿 + 交付落盘三个时机自动跑数字对照（长篇项目），
    报告入 draft 卡与交付记录
- **装配前置检查（state drift 防线）**：装配预览显示隔离区未合并登记数，
  提示"先合并再开工"（StateMemBench 状态漂移教训）

### 优化
- G0 简报注入 outline/beats/reroll/generate 提示词尾（七字段落实进上下文）
- 交付记录新增 `g0` 字段（含跳过留痕）；`checks.numbers_check` 入库；
  衔接字段默认取最近交付章的结尾钩子

### 测试
- 新增 test_longform_g0_numbers_and_probe（G0 端点/图纸确认/装配注入/
  交付对照/轻量回归）+ test_numbers_check_script（三分类/豁免/--all/
  zh_to_int 九例）；**测试 175+9**

## [0.11.0] - 2026-11-03

### Added
- **长篇模式·阶段 A：长篇项目骨架**（计划书：项目管理/计划书/工作台v0.11-长篇模式-计划书.md；
  治理框架源自灾厄前线 391 章+25 万字事故+1400 万 token 学费验证）：
  - 新建项目向导加类型选择：轻量（现状）/ **长篇连载**
  - 长篇骨架自动生成：`00_写作防线.md`（G0-G4 闸门+预算纪律模板）、
    `00_项目宪法.md`（规范层条款待填）、`bible/硬数字表.md`（数字唯一口径）、
    结构化卷纲 `outline.md`（卷+铁律）
  - **开新弧向导**（长篇项目可见）：弧名/章号区间/四字段（原作锚点/张力设计/
    勾稽点）/单章字数/**硬数字开弧定账**（账目=口径 逐条）→ 弧块落盘卷纲、
    数字账落盘硬数字表——数字唯一口径从开弧第一天生效
  - 弧块格式 `### 【弧N·弧名】（第X-Y章）` 可解析（status 端点返回弧列表/
    下一弧编号/推荐起始章）；单弧 ≤60 章；轻量项目不受影响
  - 档案编辑器白名单加 00_写作防线/00_项目宪法（治理文件网页可改）
- 后续阶段：B G0 表单+数字表进装配 / C 成本框架+看板 / D 弧末治理+交接
  （见计划书，随两处在途数据点落地推进）

## [0.10.0] - 2026-10-24

### Added（完整工作台最后一程：不开 agent 的用户全程网页走通）
- **新建项目**（POST /projects/create）：一键生成写作骨架（manuscript/bible/
  style/sessions + characters/world/names/outline 模板）+ 可选风格包钉扎
  （export 单文件 + 版本注头，read_pinned_pack 协议）+ 可选 canon 包钉扎
  （terms 快照）；创作页「＋ 新建项目」弹层（选包列表可跳过）
- **开始引导面板**（创作页顶部条件渲染）：四步 checklist——配 key → 选
  写作模型 → 建项目 → 写第一章；已完成步打钩，全部完成自动隐藏（老用户
  无感）；未完成步带直达链接/按钮
- **项目档案编辑器**（/app/bible，导航新增）：bible/（人物/世界/names/
  伏笔）+ canon/（术语表）+ outline.md 的网页编辑——与 agent 侧完全同源
  （就是文件，改完下次装配生效）；JSON 保存前合法性校验；六种模板一键
  新建（已存在 409 防覆盖）；白名单 + 穿越防护；canon 包钉扎按钮
- **章节管理**（历史页）：改名（保留章号、非法字符消毒、同章号目标冲突
  409）/ 删除（进 manuscript/.trash/ 可恢复，confirm 双确认）

### Fixed
- 测试顺序依赖三连（新测试全部独立项目自足——共享"测试项目"互相污染的
  老坑又踩，本次彻底隔离）

## [0.9.5] - 2026-10-24

### Added
- **历史与成本页**（/app/history）：每章交付快照（sessions/）变网页——章节
  卡片（时间/字数/模型/本章累计 tokens/门禁徽标：指纹·AI腔·收尾）+ 详情
  折叠（立意/拍子/fp 首行/收尾判定/正文预览，全文不搬）+ **每章消耗条形图**
  （session_tokens 真实总账，纯 CSS 零依赖）+ 累计汇总；穿越防护
- **config 写前备份**：save_config 自动留 .json.bak（key 文件损坏/误删有救）
- README 更新至 v0.9（特性补工作台全家/快速开始加 bat 入口/路线图重写）
- style-apply 技能补"网页等价"说明（两路共享文件协议可混用）

### 验收
- **记忆链真实验收（代劳第 4 章《进城》）**：装配锚定 003 ✓ → 全链 169s/
  5 调用 87k tokens（模型已换非思考：生成 23s 无重试）→ 修订后 4/11、
  收尾 ✓、AI 腔 0 → 记忆登记 14 条（风险分级正确）→ 全合并 → **第 5 章
  装配出现"记忆·前情提要"块——闭环成立**；成本对比：换模型后单章约降一半
  （见 evals/calibration.json → memory_chain_v090_real）

## [0.9.4] - 2026-10-24

### Changed（UI/UX 打磨——联网参考 2026 工具类应用做法后落地）
- **全局视觉升级**（build_site CSS，静态页与 app 页共享一份）：
  设计令牌化（--accent-soft/--radius/--speed）；输入/选择器统一 focus 焦点环
  （可访问性基线）；按钮 hover/active/disabled 三态过渡；暗色滚动条；
  表格行 hover；::selection 高亮
- **导航分组**：「浏览」（门户/包浏览/canon/判读台）与「工作台」（创作/蒸馏/
  模型配置）两节 + 品牌圆点；active 态改浅蓝底高亮；210px 侧栏
- **表单对齐**：`.panel label` 改纵向布局（标签在上、控件在下）——创作/
  蒸馏/配置页的表单从行内参差变整齐网格；`.verdict label` 行内保护
  （判读台 8×4 单选不受影响，浏览器实测）
- **toast 轻提示**：全局 showToast（右下角，good/bad 分色，自动消失）——
  创作/蒸馏页 15 处高频 alert 替换（错误不打断、成功有反馈）；
  confirm 类（交付/修订/盲测确认）保留原生
- favicon（SVG data-uri，✒）；footer 分段布局（版本 | 安全提示）
- 静态站点 layout 同步（nav 分组/版本 footer/favicon），重建后判读台
  8 轮×32 单选实测完好；浏览器截图验证创作页/判读台

## [0.9.3] - 2026-10-24

### Added（阶段 D 小件三连）
- **卷级大纲注入**：项目 outline.md（## 卷 / ### 章概要）→ 装配新增
  "大纲·卷内位置"块（卷主题 + 前一章/本章/后一章概要，后章标注"勿剧透提前"）；
  next_chapter 返回 outline_hint（该章已有概要时提示）
- **局部改写**（POST /rewrite）：粘贴片段 + 一句指令 → 只改片段、其余逐字
  保留，输出整章 + 三道 advisory 门；kept_ratio 保留率守护（<0.6 红字警告
  "模型动了片段之外的内容"）；prevText 存档走 diff 视图
- **导出合并**（POST /export）：manuscript 按章号区间合并单 txt 下载
  （内存返回不落盘，UTF-8 文件名）

## [0.9.2] - 2026-10-24

### Added（阶段 C 装配 World Info 化）
- **常驻条目双通道**：bible 块内 `<!-- resident -->` 标记，或 names.json
  `tier: core` 实体——无需关键词命中，永远注入（kind 带 ·常驻 后缀）
- **递归关联（深度 1）**：未命中块的实体名出现在已命中块文本中 → 关联注入
  （例：关键词"韩天宇"命中人物块，块内提到"铜币"→ 铜币块自动带入）
- **优先级裁剪**：常驻(0) > 直接命中(1) > 递归关联(2)——预算不够先裁关联，
  重要记忆活到最后；无标记项目行为不变（向后兼容）

## [0.9.1] - 2026-10-24

### Added（阶段 B AI 腔检测——第四道 advisory 门）
- `scripts/ai_cliche_check.py` + `ai_cliche_words.txt`（三档可扩充词表：
  口头禅/句式模板/意象套话，初始 40+ 词）：密度（次/千字）分级判定
  （<1.0 通过 / ≤2.0 提示 / >2.0 警告），零第三方依赖
- **包级豁免**：风格包 limits.md `## AI 腔豁免` 节——该作者本就常用的词免报
- 挂进创作环三路门禁（generate 同步/流式、revise），稿卡报告区三道并列；
  CLI 等价：`python scripts/ai_cliche_check.py <文本> [--pack <包>]`

## [0.9.0] - 2026-10-24

### Added
- **记忆接入创作环**（v0.9 计划书阶段 A；对标 NovelCrafter Codex
  progression——复用自家 MCP 记忆层，零协议发明）：
  - POST /app/api/memory/delta：交付后自动登记——judge 路由从正文+拍子提取
    digest/状态变更/伏笔（每章 ~2k tokens），Store.propose_delta 入隔离区；
    **风险由脚本 _auto_risk 分级**（core 实体=high），不由模型自评
  - GET /memory/pending：隔离区按风险分组视图（🔴逐条确认/🟡批量/🟢直并）
    + 老化提醒；POST /memory/merge：中/高风险 force 门（UI 双按钮）
  - **装配自动带前情**：assemble 注入"记忆·前情提要"块（最近 3 章摘要+
    未回收伏笔，来源 style/memory.db·recap，预算可裁、预览可见）——
    立意/拍子/正文提示词自然获得；无 db 新项目行为不变
  - 交付后自动 sync（bible→索引保鲜）；CLI 等价 = MCP 工具原样
    （story.propose_delta/merge_delta/recap/sync）
  - digest 提示词纪律：只登记正文实际发生的变更，绝不推测补设定

## [0.8.0] - 2026-10-24

### Added
- **蒸馏台盲测验收闭环**（style-calibrate 技能网页化；步 ⑤.5）：
  新蒸馏的包从此在网页上即可完成质量度量——"产出包 → 测出胜率"不再断链
  - /blind/start（job 化）：无题库先按文风档案出 3 道盲测题（写入
    tests/blind-prompts.md，可在校订编辑器改）；每题**带包/裸各生成一段**
    （带包臂注入 card+profile+lexicon+limits 档案上下文），随机打乱甲乙
  - /blind/session 判读视图：只给甲/乙文本与期望特征 checklist——
    **绝不外带 packed 标记**（防泄漏，测试锁死）；网页上选"更像作者的是
    甲/乙/都不像"，逐轮判完揭示答案与胜率
  - 胜率自动入 evals/calibration.json（web_blind_<包>_<日期>，与判读台
    同账本）；对局记录 tests/blind-session.json gitignore（工作数据）
  - 账本入 <包>/cost.jsonl；盲测消耗 7 次调用（出题 1 + 对局 6）
  - validate 的"缺 tests/（盲测用例）"警告自此有了网页产出路径

## [0.7.3] - 2026-10-23

### Added（打磨五连：版本可见 / 章节防呆 / 批次不丢 / 进度可见 / 修订可对）
- **页脚版本号 + 启动横幅**：三个 app 页页脚显示 v{版本}（CHANGELOG 解析），
  launch 打印版本与端口并提示"页脚对不上=旧实例没关"——两次旧实例事故的
  直接防复发
- **章节号自动推荐**：GET /app/api/next_chapter（manuscript 最大 NNN+1），
  切项目自动填推荐值并清 title/keywords 残留——章节号错乱会让"上一章结尾"
  锚定失效（用户前三章全填 1 的防呆）
- **草稿批次落盘**：slots 增 drafts 字段（最近批次全量轻量序列化），
  生成/修订/挤批后自动写回；切回方案恢复全部批次（收尾检查需重跑有提示）
  ——刷新/关页不再丢多批草稿
- **蒸馏 job 化**：/read_start 与 /gen_draft_start 后台线程 + /job/{id}
  2s 轮询，实时显示当前步骤（"范例生成中（低温）"…）；同步端点保留
  （CLI 等价）；job 经 thread-local 注入不污染端点签名
- **修订 diff 视图**：修订后的稿卡内嵌"对比修订前"折叠面板——段落级 LCS
  对齐，红删除线/绿新增，改了什么一眼可核

## [0.7.2] - 2026-10-23

> **真模型全流程验收（luxun 62 篇 → local/luxun-webtest v0.1.2）**：精读
> 溯源逐篇、范例引文零剔除、motif 全剔经校订改高频单字后保留 看/眼；指纹
> 核心指标与手作包一致（句长 P50 同 19.0），未入选篇《药》双包 fp_check
> 均过。明细见 evals/calibration.json → web_distill_v072。

### Added
- **蒸馏工作台阶段 C：草案生成 + 逐节校订 + 定稿**（计划书阶段 C；步 ④⑤⑥
  点亮，"加新作者"全流程闭环）：
  - 草案生成（/gen_draft，4–5 次低温调用）：exemplars（**引文逐字校验**——
    不在语料中的伪造引文整条剔除，溯源硬保证）→ 九章 profile（引用范例
    序号 + 实测锚点）→ card/lexicon/limits 三件套（JSON 包装）→ thought
    （可选）+ motif_count --write 脚本验证；pack.json 补全诚实
    corpus/provenance（从 ingest 记录回填）
  - 逐节校订：档案白名单（6 个 md）GET/POST /file，页面分文件编辑器
  - 定稿（/publish）：**validate 必须通过**否则 400 拒绝；选层落位
    （公版 stylepacks/ 顶层 / 本地 stylepacks/local/ + license_note 自动写）；
    status 字段移除后即刻对创作页/站点/装配可见
  - 成本预告先行（/preview_draft），账本入 <包>/cost.jsonl

### Fixed
- **gen_draft 的 top_chars 解析**（真语料验收实测）：fp_extract.json 的
  top_chars 是 [{char, per_1k}...] 列表而非字典，`.keys()` 崩溃——mock 流程
  未写该文件故未暴露；已兼容两形态并加回归锁（测试 160+9）
- **build_delta --layered 补写顶层混合 metrics（derive_thresholds 带容差）
  + reference 实测快照**——此前分层指纹只有 genres 层有容差叶，顶层恒缺，
  新蒸馏包永远过不了 validate（"带容差的指标叶仅 0 个"）；手作包系人工补写，
  此为引擎级缺口
- pack 脚手架修正：provenance 须为数组、license_note/changelog 必备字段
  （validate 硬性要求），阶段 A 起即正确

## [0.7.1] - 2026-10-23

### Added
- **蒸馏工作台阶段 B：采样精读 LLM 化**（计划书阶段 B；/app/distill 步 ③ 点亮）：
  - 自动选样：首/中/尾各 1–2 + 对话密集/叙述密集各 1（去重上限 8，入选理由
    累积制如"开头、对话密集"）；剔除名单自动继承体检结果
  - **成本预告硬门**：烧模型前必看"N 篇 / X 字 / 单次或 map-reduce K 块 /
    预计 ≈Z tokens"，confirm 后执行；选样增减实时重算预告
  - 精读：≤100k 字单次注入；超出自动 map-reduce（60k 字/块，块观察 ≤800 字
    五项 → 主汇总融合；无据可提的思想四问置空，不得编造）
  - 输出六问题+思想四问 JSON → <包>/analysis.json（工作数据，gitignore；
    页面可编辑保存，草案阶段将引用）
  - 提示词与选样算法独立成 web/distillation.py（提示词纪律同技能 2 节：
    每判断溯源篇目、不搬运原文）；D3=写作路由、低温 0.3
  - 蒸馏账本：<包>/cost.jsonl（skill="web-distill"，gitignore）
- 新增 web 模块依赖隔离校验不变（引擎层零依赖；distillation.py 纯标准库）

## [0.7.0] - 2026-10-23

### Added
- **蒸馏工作台阶段 A**（计划书：项目管理/计划书/工作台v0.7-蒸馏工作台-计划书.md；
  /app/distill，六步状态机，本版点亮前两步，全程零模型调用）：
  - 语料浏览/入库：downloads/corpus 作者与作品识别（长篇 chapters 布局 +
    短篇平铺布局）；raw-body 上传调 ingest.py，返回章节数/字数/编码/去广告行数
  - 指纹与体检：fp_extract + build_delta --layered 编排；逐样本指标表 +
    **离群 z≥2 自动预勾选剔除**（有 stats 读缓存，平铺语料现场计算）→
    剔除重建指纹（fp_extract/build_delta 新增 `--exclude`）
  - **草稿包（status: draft）**：蒸馏台一键建包 scaffold；三处消费枚举过滤
    （创作页包下拉、装配入口 400 拒绝、包浏览站点 iter_packs）；
    validate_pack 对全新包可用（build_delta 不再要求 fingerprint.json 预存）
  - 每个操作响应带等价 CLI 命令；侧栏当前包预览 + validate 面板
  - 真语料验收：downloads/corpus/luxun 62 篇平铺——5 个离群自动标出，
    剔除后 57 样本重建，essay 26/narrative 31 双层留一线均标定
- 阶段 B（采样精读 LLM 化）/ 阶段 C（草案生成+定稿）见计划书，后续版本

## [0.6.8] - 2026-10-23

### Fixed
- **消耗账目修复**（用户"消费变高"排查的收尾）：cost.jsonl 此前只记交付稿
  最后一次调用的 tokens，修订中间批/判官等消耗被低估——新增
  session_tokens/session_calls 字段（本章会话所有调用的真实总账），
  sessions 记录同步带 session_totals；交付完成行显示"本章累计 XXk tokens /
  N 次调用"

### Changed
- dist 重打至 v0.6.8（此前停在 v0.5.1）

## [0.6.7] - 2026-10-23

### Changed
- 修订篇幅纪律补上限（不得低于 90% **也不得超过 120%**——实测 2500 字目标
  修出 3324 字超限 33%，防缩水条款矫枉过正的回摆）

### Added
- 交付守卫：收尾检查未跑或修订后未重跑 → 交付前 confirm（思想层硬性条目；
  实测 001-003 修订把旧判词作废后未重跑就交付，checks.ending 为空）
- 截断重试成本提示：一稿经 ≥2 次截断重试 → 完成时明示"消耗 XXk tokens、
  耗时约 ×N——建议换非思考模型"（001-003 实测单次修订 50.9k tokens，
  7000/14000 两档被推理打满截断、28000 档才完整）

## [0.6.6] - 2026-10-23

### Added
- **方案槽（5 槽，装配可重放）**（用户需求："保留五次装配预览，方便对创意
  满意但正文不满意的文章重修"）：
  - 每次「装配预览」成功后**自动入槽**：同指纹（项目|包|章|关键词|挡位）
    复用原槽不占新坑；否则空槽优先、环形挤掉最旧**未锁定**槽；5 槽全锁
    → 409 提示解锁。槽文件 `项目/slots/slot-1..5.json`（gitignore 同
    sessions），CLI/agent 可直接读写（文件协议红线）
  - 槽随流程生长：锁定立意/生成拍子表/产出草稿持续写回；槽名自动取立意
    方向名，可手动命名/锁定/清空（芯片内联操作）
  - **切回方案 = 重放装配（零模型调用）** + 回填立意/拍子/调子/锚点/字数
    挡位/上次稿；包版本不一致给黄字提示（槽记捕获时版本）
  - **草稿从覆盖改累积**：同一方案连点生成不再互相抹掉，按批累计（批N·稿M），
    保留最近 5 批，采用稿下拉跨批挑选；服务端每槽存最新一稿供刷新后查看
  - 交付记录补 keywords 字段（历史会话自此可精确重放装配）

## [0.6.5] - 2026-10-23

### Fixed
- **修订缩水根因修复**（真实事故：2500 字稿修订后剩 1099 字，尾部停在
  半句对话上）：deepseek-flash 在修订任务上推理消耗上万 token，7000/14000
  预算两度打满（finish_reason=length、completion=21000）——而 v0.6.2 的
  重试链只认"空正文"，**非空截断被当正常结果放行**。现在：
  - chat()：finish=length 一律加倍重试（阶梯 4 档，取最长结果），截断与
    空稿同等待遇
  - 流式路径：截断 → 非流加倍链回退 → **replace 事件**整稿替换部分稿
  - 修订预算 ×2（整篇重写输出≈原文，思考型模型推理吃同一预算）
  - revise_prompt 防缩水条款：原文约 N 字、修订后不得低于下限 90%、
    **严禁靠删情节/删对白/缩写场景来"合并碎段"**
  - 稿卡新增红色截断徽标（finish_reason=length 可见）
- 顺手：新章句长收敛验证通过（001-002-测试 fp_check ✅ 全项、Delta 1.06；
  基线 001-测试 4/11 不达标）——雨落包 0.2.1 句长纪律 + 字数挡位生效

### Added
- **调子/锚点初始选项**（用户需求）：GET /app/api/presets——调子取包
  registers.md 分区名（如鲁迅包 沉郁哲思/冷峻讽刺/温情回忆；无 registers
  的包回退通用建议集），锚点取项目 sessions 实际用过的 canon_anchor
  （新→旧）；前端 datalist 下拉建议，仍可自由填写；切换项目/包自动刷新

## [0.6.4] - 2026-10-23

### Added
- **流式输出（SSE）**：model_client.chat_stream()（OpenAI 兼容 delta 流；
  供应商不认 stream_options 自动裸流重试；usage 缺失按字数粗估）+
  /app/api/generate_stream 与 /revise_stream 事件流（session/draft_start/
  delta/reasoning/status/draft_done|revised_done/error/all_done）。
  正文与修订逐字上屏、实时字数、思考型模型显示"思考中"。
  **流式不提高 max_tokens 上限**（上限仍由挡位换算与模型/供应商封顶决定），
  但读超时按 chunk 间隔计——超长生成不再被"整段等待"的 240s 掐断，实际
  可用输出更接近上限。空稿防御链完整继承：流式空稿 → 非流加倍回退 →
  error 事件带对策，绝不吐空 draft_done。旧非流端点保留（插件红线：CLI/脚本
  等价路径不动）
- **创作页重排"生成现场"右侧栏**：双栏布局（步骤流左 / 生成现场右，窄屏
  自动叠放）；侧栏含六阶段状态条（装配→立意→拍子→生成→门禁→交付，随操作
  点亮）、模型路由标签、目标字数、调子/锚点/稿数/流式开关、生成按钮、
  草稿卡片流式渲染、采用稿交付区；拍子表就绪前生成按钮禁用

### Fixed
- 多稿流式下 draft_done 全量重绘会抹掉仍在流式的其他稿卡片——改为只换
  本稿卡片（refreshPick）

## [0.6.3] - 2026-10-23

### Added
- **创作环字数挡位**（用户需求）：装配页新增「字数挡位」——预设 短章≈1500 /
  标准≈2500 / 长章≈4000 / 特长≈6000 四挡 + 自定义（300–20000）；贯通全环：
  - 拍子表/单拍重掷提示词按目标字数配拍（"拍子数量与详略按此配比"）；
  - 正文提示词带合格下限/上限（85%/120%，"不为凑数注水，也不提前收笔"）；
  - **max_tokens 按字数换算**（1 字≈0.75 token 与 assemble 同口径 +600 余量，
    只增不减覆盖 prose_max_tokens 配置兜底）——长挡位不再被 3500 上限截断；
  - "按报告修订"同样承接（未显式指定时按当前稿实际字数）；
  - 交付时挡位入 sessions 记录（复判可知当时目标）；越界值按未指定处理
- 装配预览摘要显示「目标正文 ≈ N 字」

### Fixed
- 测试顺序耦合：test_empty_key_preserves_stored_key 曾把 routing 清空不恢复
  （此前无后续测试调用 /generate 而被掩盖）——改为保留当前 routing 再提交

## [0.6.2] - 2026-10-23

### Fixed
- **思考型模型空稿全链路防御**（真实事故：deepseek-flash 生成正文时把
  3500 tokens 全花在内部推理上，content 为空、finish_reason=length；
  空稿一路流过三道门——fp_check 除零吐整屏堆栈、borrow_check "0 字"、
  ending_check "原文为空"——最后还能交付成 `001-.md`（0 字节））：
  - model_client.chat()：捕获 finish_reason/reasoning_content；空正文自动
    加倍预算重试（最多 2 次，3500→7000→14000）；仍空则报可行动对策
    （换非思考模型/供应商侧关思考/调大正文 max_tokens），绝不返回空稿；
    usage 记账含重试真实消耗，带 finish_reason/retries 诊断字段入 sessions
  - /generate、/revise 经 _do_model 统一兜底（ValueError→502 明示）；
    /save 拒绝空稿（400）+ 空题落「未命名」+ 文件名非法字符消毒
    （`\/:*?"<>|`→`_`，结尾点/空格剥离）
  - fp_check：空输入干净报错退出码 2（不再 ZeroDivisionError）；
    splib.char_rates 空文本守卫
  - create.html：稿卡显示「正文 N 字」，空稿红色警告，前端拦截空稿的
    修订/交付，空题交付前 confirm

### Changed
- 会话记录 tool 字段 web-create v0.6.0 → v0.6.2（v0.6.1 漏更）

## [0.6.1] - 2026-10-11

### Added
- **创作环"按报告修订"迭代步**（对照验收差距归因 #1，S3 打磨首项）：
  /app/api/revise 端点——把 fp_check/borrow_check 报告原文 + 当前正文喂回
  写作模型定向重写（情节/拍子/笑点/收尾全部保留，只动语言层），改完自动
  重跑两道门；每稿显示"已按报告修订 N 轮"徽标。网页流程自此具备与 agent
  协议同款的 fp_check 驱动自检迭代
- **雨落三千河包 0.2.1：句长纪律入档**（对照验收差距归因 #2，双仪器证——
  本地包盲测判官警告 + 对照验收 fp_check 4/11 超差全部是句长/段长）：
  profile 句式与节奏加"短段签名有下限"（段中位 ≥16/句中位 ≥12，连续超短段
  ≤3 行后须落地段）；limits 首条警告同款。提案经用户批准应用

### Changed
- yuluosanqianhe pack.json 0.2.0 → 0.2.1（changelog 记双仪器证据）

## [0.6.0] - 2026-10-07

### Added
- **工作台 v0.6.0「创作环最小闭环」**（计划书：项目管理/计划书/工作台阶段1-创作环最小闭环-计划书.md，
  r4 阶段 1+2 重切执行）：
  - **模型配置层**：多 provider（OpenAI 兼容）、测试连接（GET /models）、
    **按模块路由**（写作/判官/批改分开绑，判官建议异源）；key 只存服务端
    web/config.local.json（gitignore），GET 接口脱敏、页面永不回显
  - **创作环状态机**（/app/create，蓝本 = style-apply 两级共创照搬）：
    装配预览（所见即所发，每项带来源+token 估算；记忆注入预算制最小版）→
    立意确认（2–3 方向，引 thought 条目）→ 拍子表（可编辑/单拍重掷）→
    生成（1–3 稿并选）→ 三道门（fp_check/borrow_check advisory 报告 +
    判官模型收尾检查）→ 确认交付 → 落盘 manuscript/ + sessions/（含装配
    快照可复判，sessions 自带 .gitignore）
  - **工作区数据层**：项目发现（manuscript/bible/style/canon 标记）、
    钉扎协议读取（style/pinned-pack.md 版本注头）、cost.jsonl 对齐 cost.py
    同账本（web-create 条目加 model/tokens 附加字段）、会话 token 护栏
  - **launch.py 升级**：首次运行自动安装 Web 依赖（requirements-web.txt，
    依赖隔离 web/ 引擎层零依赖不变）；默认全模式（FastAPI + 静态站点同源），
    --static-only 兜底；固定端口 8765 优先
- tests/test_web_server.py（9 项）：**mock 模型服务器全流程 e2e**
  （装配→立意→拍子→重掷→生成→收尾→落盘，零网络）+ 红线断言
  （key 不入接口/会话记录/git、路径穿越拒绝、仅本机绑定）；
  总测试 116+9 → **125+9**
- web/requirements-web.txt；技能引用修正（style-apply/style-setup 的
  packs/narrative → docs/references，v0.5.3 遗留）

### Changed
- 静态导航增"模型配置/创作"入口（file:// 模式为死链，服务器模式生效）

## [0.5.3] - 2026-10-07

### Added
- **风格包统一管理死规矩落地**（用户立项；项目管理/计划书/风格包统一管理-执行规划.md）：
  `stylepacks/` = 作者风格包唯一家园，顶层公版层（入库）+ `local/` 本地层
  （非公版，gitignore，工作台可枚举、永不入库/入 zip）；`canonpacks/` =
  canon 包唯一家园；语料唯一家 `downloads/corpus/`（工作区级）
- 网页工作台枚举 local 层：包列表与详情页带"[本地·不得公开再分发]"徽标，
  本地三个包（无双兔/游鱼怀月/雨落三千河）入库面即现在站点可见
- 仓库结构守卫测试：stylepacks/ 顶层子目录必须含 pack.json（local/ 豁免）

### Changed
- 工作区重整：三个非公版包迁入 stylepacks/local/（原散落于仓库外
  stylepacks-ciweimao/、stylepacks-fanqie/ 项目目录内）；根 corpus/ 并入
  downloads/corpus/legacy-root-corpus/（33 文件零丢失，含 zhuziqing 旧
  ingest 分章版）；`packs/narrative/REFERENCE.md` → `docs/references/narrative.md`
  （第三个 packs 目录消除，两包 limits.md 引用同步）
- pack.py dist 打包排除 local/；.gitignore 加 stylepacks/local/；
  README 仓库结构节更新

## [0.5.2] - 2026-10-07

### Added
- **网页工作台阶段 0**（计划书 r4 落地；原定版本号 v0.5.0 已被 canon 层占用，
  顺延为 0.5.2；零依赖静态站点）：
  - `web/build_site.py`：判读台（8 回合人工判读，纯客户端 localStorage +
    导出 JSON）/ 包浏览器（全档渲染）/ 测量可视化（指标容差表、LOO 留一线、
    motif SVG 横条图）
  - **双击入口**：`启动工作台.bat` → `web/launch.py`（构建站点 + http.server
    仅绑 127.0.0.1 随机端口 + 自动开浏览器，无需手动命令行）
  - `scripts/migrate_human_judging.py`：盲测人工判读包 md → 双 JSON，守卫断言
    （8 回合 / 带包臂序列 乙甲乙甲甲乙乙乙 / 子代理战绩 6/8）；
    `evals/human_judging.json` 入仓库，**答案卷 gitignore**（红线 6）
  - `scripts/score_human_judging.py`：判读导出计分——辨认带包臂命中率 +
    与子代理判官一致率（同源偏差度量），答案卷缺失时给出补救指引
- `tests/test_web.py`（12 项）：产物无全文（语料 250 字窗口断言 > 短引上限）、
  判读页无答案、封闭构建、仅本机绑定、bat 入口接线；总测试 100+9 → **112+9**
- `web/README.md`；计划书：项目管理/计划书/网页控制台-计划书-r4.md（代码库核实版）+
  阶段 0 执行规划

### Changed
- `.gitignore`：`web/site/`、`evals/human_judging_answers.json`

## [0.5.1] - 2026-10-07

### Changed
- **zhuifang 包 0.1.0 → 0.2.0（四路联网核查 + 仲裁子代理终审）**：
  - 艾莫号前身**定稿格里芬资产说**（2064 穆罗梅兹行动已作格里芬移动指挥车）；
    "医疗舰说"（环太平洋救援组织 / 盖亚扩散 / 遗迹战争）经三源核查判定为
    百科不实内容，明令不得使用
  - 存在性清账：黛烟存在（季风乐队，QBZ-95 烙印）【强】；弗必安存在（坍塌辐射
    计量单位，黑区 >10000 / 白区 0）【中】；"委托人"仅为第三章登场角色称谓，
    禁止当组织名使用【弱】
  - **OOC 红线定稿（附证据强度）**：闪电 / 纳美西丝 / 克罗丽科 / 维普蕾 / 寇尔芙
    五人。关键发现：原作寇尔芙为"人家"自称 + 夹子音撒娇腔 + 讨好型 + 对瓦良格帮
    灭队之仇——与灰区回声既有写法严重 OOC，仲裁裁定**渐进迁移**：第 1—11 章
    不改稿，第 12 章起引入原作声线，迁移说明入项目 bible/characters.md
  - 漂移词反哺 ban：抗辐剂 / 信用点 / 污染区字母分区；conventions 增晶条计价纪律

### Data
- **canon 盲测扩样 n=4 → n=10**（canon_blind_v050）：canon 臂 **8 胜 2 负**
  （两负均中置信，八胜含七局高置信）；场景覆盖委托/侦察/帮派/生骸/日常/检查站。
  判官噪声两例入档（黑区、非军事力量管理局被误判为非原作——判官裁词应以包内
  facts 为准，v0.5.2 可给判官发事实卡）

### Added
- 灰区回声第 12 章《失效坐标》：新红线端到端验证（寇尔芙"人家"声线迁移首章、
  弗必安读数、晶条记账）；consistency-check 增量模式首跑——canon/names/timeline
  三脚本全绿 + 模型审查（P0 零、P1×2、P2×6，全部按报告修复后复检通过）

测试：100 项全绿（无新增用例，canon 分支回归通过）

## [0.5.0] - 2026-10-06

### Added
- **canon 层（二创约束引导，计划书 v0.5）**：新增 `canonpacks/` 包类型，与风格包
  对称——card / facts / conventions / terms.json（must/allow/ban 三级术语表，
  错译进 wrong 变体）/ characters.json（roster+tier+OOC 红线+OC 接口规则）/
  sources.md（URL+抓取日期审计）。首包 `canonpacks/zhuifang`《少女前线2：追放》
  （闪电小队 roster、2074 时代锚点、黑→红→黄→净化区→绿→白污染分级）
- **canon_terms_check.py**：must 覆盖（volume/chapter 两档阈值）+ ban/错写
  0 容忍 + 千字浓度 advisory（防硬塞指标）；7 项行为测试
- **validate/export/pin 的 canon 分支**：pack.json.kind=="canon" 分派；canon 校验
  （必备文件、cast_policy、ban 必须给理由、core 角色红线缺失警告、sources 审计、
  引文 >100 字违反摘要纪律、注入启发式复用）；canon 单文件导出
  （CANONPACK-SINGLE-FILE）；pin 同步写 canon-terms.json 快照（_pinned_from 记版本）
- **技能（双副本同步）**：style-setup 第 3.5 步"原作锚定"（二创分支：联网双源
  核对 → canon 档案逐节校订 → validate → pin → outline 双轨声明"事件原创、
  设定恪守"）；style-apply 上下文协议第 6 条（canon 层必载）、拍子表"原作锚点"行、
  验收加 canon 检查、自检表加"canon 检查"项；consistency-check 第一层
  canon_terms_check、第二层"原作保真"（OOC 以 canon 人物卡优先、facts 红线 P1、
  OC 接口核查）；stylepack list/pin 支持 canon 包
- schemas/canonpack.schema.json

### Fixed
- 灰区回声 P0（案例修复，reviews/p0-验收报告.md）：埃尔莫→艾莫号错译 47 处清零、
  "沙暴"→"坍塌风暴"46 处规范；第 8—10 章连续性接缝修复（旧人形下落三版统一、
  存储盒"只够播放一次"与第 9 章长录音矛盾、文件【她们】穿越引用、第 10 章开头
  重演返程段删除）

### Data
- canon 盲测 canon_blind_v050（项目 style/calibration.json）：n=4，canon 臂
  3 胜 1 负（负局中置信，胜局均高置信）。发现：无包臂凭模型先验也能产出
  琼玖 / 佩里缇亚 / ELID——canon 层的边际优势在**术语体系化与委托-结算经济
  脚手架**，与计划书 v0.5 论点一致；n=4 只记趋势

测试：95 → 100（canon_check 7 项 + validate/export canon 5 项）

## [0.4.2] - 2026-10-06

### Added
- **borrow_check.py 借句初筛**（遗留 #8 机器初筛层）：草稿 vs exemplars
  引文 ≥12 字逐字重叠检测（规范化后滑窗 + 最大重叠延展），exit 0/1 可作
  交付自检可选门；**初筛不是终判**，化用/骨架雷同仍靠盲测与人工判读兜底；
  6 项行为测试 + GBK 全入口冒烟纳入（总测试 82→88）
- style-apply 交付自检增"借句初筛"项（双副本同步）
- **迷你辨认盲测**（calibration.json `recognition_v043`）：profile r2 后
  2 回合，辨认 2/2、乱真归属 2/2——r3 后 zhuziqing 辨认分歧的有利数据点
  （n=2 只记趋势）
- evals/cases.md Case K

### Changed
- **zhuziqing 散文层与思想层同步重蒸馏（遗留 #1 闭环）**：profile.md r2
  （10 篇逐条重裁决、每条指认篇目）——对话改按关系分层（推翻 4 篇时代
  "对话极少"）、议论改三通道条件项（对齐 thought r3）、结构补纪游列叙/
  忆人三叠/自省忏悔三构型、情感谱扩、"你"呼告升高频；exemplars 8→12 条
  （童语成串/对答窘态/幻灭收束/实事托住直抒收束）；lexicon（叠词/纪游词
  扩充、议论条改条件项）、limits（语料描述改 10 篇四路、分层对话入"可
  模仿"）、card 同步；pack.json 0.4.3。指纹不动（已 n=10，essay LOO 1.486）

## [0.4.1] - 2026-10-05

### Added
- **三仪交叉终审**（用户授权子代理终审）：自由辨认（不点名作者）+ 判据合规
  盲评 + 乱真归属（真迹锚），加 r2 对抗审查——全部由互不共享上下文的子代理
  执行，结果入 calibration.json `final_verdict_v040`
- 结论：**luxun 三仪俱证**（辨认 6/6 vs 3/6；合规 6×18/18 vs 均值 13.67；
  归属 6/6 vs 2/6 同手）——思想层带包增益成立，且带包方差为零（每篇都保持
  在判据内）；**zhuziqing 分歧如实记录**（辨认反向/归属混合/合规无区分）

### Changed
- **thought.md r3**（对抗终审 3 条改判采纳）：社会冲突回条件项、虚构禁写
  限定散文体、"居高临下"改"禁居高临下而无自省"、议论三条件改三选一、
  反讽三分、体罚/刑罚拆分、低频姿态条目标注"不必强求"、师友作镜改
  "引他人评价自照"；profile.md 同步列为遗留待办

## [0.4.0] - 2026-10-05

### Added
- **zhuziqing 语料 4→10 篇（Case G 收官）**：桨声灯影里的秦淮河 / 绿 /
  白种人——上帝的骄子 / 儿女 / 冬天 / 南京，全部来自中文维基文库（当日
  可达性恢复；MediaWiki API wikitext + opencc t2s 本地简体化 + 繁体标记字
  断言 + 语境核查），逐篇 provenance
- downloads/_raw/fetch_zhuziqing_wikisource.py：抓取/清洗/转换管线（可复跑）
- thought.md r2 重蒸馏（zhuziqing）：10 篇精读逐条裁决 4 篇时代的结论——
  **2 条弱禁用被推翻**（社会冲突/多人对话强冲突）、2 条降条件项、1 条转正
  硬规则（虚构人物禁写）、新增 3 条；motif 词表 12 词重算（旧表 5 词系
  4 篇选样假象，跌破剔除线删除）
- **思想盲测续跑**：4 回合（luxun 2 + zhuziqing 2）——带包 3/4，累计 6/8；
  zhuziqing r2 两轮全胜，判官获胜理由即 r2 判据（thought_blind_v040）

### Changed
- **跨包归因仪器修正（重要）**：复测发现旧口径（各自包 top-150 字符集
  Delta）随基准选择**翻转方向**（评测集 luxun 0/5、大语料又 62/62，p 全不
  显著）——v0.2.8 的 7/9 与 zhuziqing n=4 的 2/4 均属仪器伪影，如实撤销；
  改用**度量空间 + 全局基准**（Case J 同源机器）：**13/15（0.867），
  p=0.004，zhuziqing 侧 9/10**——"补齐后回 ≥0.9"的预测在正确仪器上兑现。
  test_cross_validation 重写（test_delta.py），evals Case G 收官补记
- zhuziqing essay 层留一线 2.112 → 1.486（n=10）；pack.json 0.4.1；
  82→84 项测试全绿

## [0.3.1] - 2026-09-30

### Added
- **registers_dryrun.py**：调子分区统计真实性检验 CLI——层间归因率 + 置换检验
  p 值 + 候选分法（k=现状 / k-1 合并）对照表；**全局基准纪律写死在代码里**
- splib 归因/置换机器：`parse_registers_md`（含标定行）、`match_labels_to_files`、
  `build_register_layers`、`build_metric_matrix`（12 维句法度量向量）、
  `attribution_detail / permutation_test`（固定种子可复现；预计算矩阵让
  1000 次置换秒级可跑）
- `tests/test_stratum.py`：阳性对照（合成双维可分语料必须显著）、阴性对照
  （随机标签必须不显著）、种子确定性、标定行解析、dry-run CLI 冒烟

### Changed
- **R1 检查点 1 裁决（负结果）**：层间归因 + 置换检验（预注册判据，全局基准）
  全轴不显著（情感轴 p=0.336 / 节奏轴 p=0.278）——六分区全部标"仅路由"，
  指纹分区不落地（build_delta --registers / fp_check --stratum 按计划不实现）；
  registers.md r2 落标定状态，示范段路由（R0）不受影响
- 仪器可信度：阳性对照（文体标签，度量空间）归因 0.871 / p=0.0；阴性对照
  （随机标签）p=0.51
- 方法论产出：**基准纪律**——逐轴自建 z-score 基准曾给出 p=0.01 的假显著，
  全局基准下消失；显著性检验的基准选择必须先于看数固定
- evals 新增 Case J（R1 负结果全记录）

## [0.3.0] - 2026-09-30

### Added
- **思想层 thought.md（v0.3 主体）**：可选包文件，六节骨架——选题地平线 /
  立意动作 / 观察清单 / 意象系统 / 价值姿态 / 禁区。蒸馏对象是**思路的动作**
  （选题偏好、立意招式、观察习惯、可执行姿态指令），不是思想的内容；全部
  条目须指认 exemplars 编号或语料篇目，不能溯源的删除
- **luxun / zhuziqing thought.md 定稿**（用户逐节校订通过）：luxun 立意动作
  10 招 + 价值姿态 9 条（全部指令化，如"叙述者后退半步，让事实并置，禁直接
  评判"）+ 禁区 9 条；zhuziqing 各节**置信度逐节标注**（语料仅 4 篇，
  回避 / 禁区为弱禁用）
- **motif_count.py**：验证 thought.md 提案词表的语料频率（递归收集 *.txt/*.md），
  低于剔除线自动剔除，--write 写回 motif_stats 节 + pack.json 版本联动——
  提案是模型的，数字是脚本的（防幻觉意象）
- **fp_check --thought**：输出 motif 密度对照——**advisory，不进判定、
  不影响退出码**（测试锁定）；思想特征全部可 Goodhart（意象可堆砌），
  故永不升级为通过性指标
- **format_version 0.1 → 0.2**：schema 增 thought / registers 可选能力标记，
  可选文件缺失时全流程照常（向后兼容）
- 四技能更新（双副本）：style-analyze 思想四问（一次精读两份产出）、
  style-apply 两级共创（立意确认 → 拍子表）+ **交付声明制**、style-critique
  思想维度 + 贴标签检测、style-calibrate 思想盲测（同题材两问，判读问题 =
  "哪篇更像这个作者在思考"）
- tests/test_thought.py（13 项）+ TestGenericAuthorPipeline.test_thought_layer_cli
  （任意作者思想步端到端）；evals Case I

### Changed
- **motif 剔除线按语料规模校正**：1.5/千字为小语料防幻觉线；luxun 20.8 万字
  语料实测仅剩 3 词（月/夜/死全被杀）→ 校正为 0.5/千字（防幻觉功能不变：
  ≥0.5 即 ≥104 次出现），"头"因方位词复合流量污染计数手动剔除；
  luxun 词表 12 词、zhuziqing 10 词（全部过线）
- pack.json：luxun 0.3.0→0.4.0、zhuziqing 0.2.0→0.3.0（thought 能力声明）
- validate 对无 thought.md 的包给 1 条提示（沿计划 §6.1：0 警告升级为 1 条提示）

## [0.2.9] - 2026-09-30

### Added
- **调子分区 registers.md（R0）**：luxun 包新增可选文件——情感轴 3 分区
  （沉郁哲思 11 / 冷峻讽刺 9 / 温情回忆 7）+ 节奏轴 3 分区（对话场 20 /
  白描场 7 / 抒情场 7），61 篇逐篇标注主/次调子 + 一句依据；朝花夕拾·后记
  除名（考据跋文自述声口稀薄，不适配任何调子）。写作时按**声明的调子**
  路由示范段——只影响上下文选择，不参与验收判定（验收端指纹分区
  `--stratum` 属后续版本）
- exemplars.md 全部 12 条带「调子：」机器可读行，与 registers 示范段路由
  互为镜像；新增示范段 11（温情回忆·《从百草园到三味书屋》）、
  12（冷峻讽刺·《父亲的病》），六个分区均有示范段
- validate_pack 新增 registers 六项校验：引用完整性 / 调子值域 / 跨文件
  查重（分区名 vs profile 章节 vs 范例标题）/ 注入扫描覆盖 / 引文 ≤200 字 /
  双向一致；pack.json 增可选能力标记 `registers`
- export_pack 条件段机制：包内有 registers.md 才并入「调子分区」节
  （定位断言锁定正文区段），无则导出与旧版完全一致；v0.3 的 thought.md
  将复用同一机制
- tests/test_registers.py：14 项正负例（luxun 副本变异法）

### Changed
- MCP `stylepack.info` 返回的 info 载荷中 changelog 只保留最新一条：
  changelog 随包增长必然撑爆 2KB 返回纪律（luxun 0.3.0 实测触发
  truncated，结构性问题而非个例）
- pack.json corpus 元数据对齐 62 篇现实（v0.2.8 遗留缺口：仍列 5 篇
  19080 字）→ 集级条目 + 208,039 字 + 置信度更新；pack.json 0.2.1→0.3.0
- 技能路由：style-apply 拍子确认增加**调子声明位**、示范段按声明调子的
  分区挑选；writing 轻模式按请求中的调子词路由；`.zcode/skills/` 与
  `core/skills/` 双副本同步
- 文档面向通用 agent 宿主表述：README / usage 不再绑定特定宿主名称，
  宿主专属安装信息集中到 docs/adapters/（保留）；修复 README 指向仓库外
  设计文档的死链；路线图更新至 0.2.9 现状、技能计数修正为 12

## [0.2.8] - 2026-09-29

### Added
- **鲁迅语料扩充（Case G 主体完成）**：《野草》全本 24 篇 +《朝花夕拾》13 篇 +
  《呐喊》《彷徨》全部小说（含《阿Q正传》）共 62 篇 20.4 万字入库
  （GitHub Ac-heron/luxun，commit 固定；SSH 克隆 + git show 读对象库，
  绕开 raw.githubusercontent 不可达与 API 限流）
- 分层指纹重建（语料扩充即触发 pack.json 0.2.0→0.2.1 联动升版）：
  **essay 层 n=2→26，留一线从不可标定 → 1.677**；**narrative 层 n=3→36，
  留一线 18.99 → 1.981（收紧 9.6 倍）**——v0.2.3 时代的两大已知限制解除
- docs/corpus-sources.md 登记表更新：抓取经验（对象库读取法）、清洗纪律
  （编者脚注区整段截断、□ 缺字符保留原则）、朱自清/新作者待源状态

### Changed
- **跨包归因测试改分层口径**（test_cross_validation_layered）：每篇真迹按文体
  选层比较自包/对方包同层档案——预分层混合档案口径随 luxun 语料结构变化失真
- **如实下调归因声明**：luxun 侧 5/5 全对；zhuziqing 语料仅 4 篇（源站当日
  不可达待补），essay 层对自家作品归因余量 < 0.2，两篇误归——当前诚实下限
  7/9（阈值 0.7 + 误归清单断言）；**散文层作者鉴别结论改为"跨包相对归因"，
  绝对包络只答"是否在真迹范围内"**（背影→luxun 在 26 篇包络内通过，如实记录）
- evals Case F 更新（新线数值 + 包络宽度教训）；Case G 标记 luxun 完成、
  zhuziqing 待源

### 诚实声明
- 朱自清补篇与新作者语料：维基文库 / ccview / raw.githubusercontent 当日均
  不可达，GitHub 无全集类仓库——登记表已列备选源与最快路径（用户侧提供 txt）
- 语料不入仓库（版权红线）；本次仅包指纹与元数据入仓库

## [0.2.7] - 2026-09-29

### Changed
- **GBK 冒烟补强（codex v0.2.6 复审三条低危残留，全采纳）**：
  - timeline_check 从 --help 换成**真实工具路径**（最小 timeline.json fixture，
    断言"时间线一致"）
  - cost report 补关键词断言（"读取字符"表头）
  - 8 个 CLI 拆为 `subTest`——失败精确指认到具体 CLI，不再一揽子报一个 failure
- windows-gbk CI job 导出补齐 zhuziqing，与 ubuntu job 完全对齐

## [0.2.6] - 2026-09-29

### Fixed
- **story.py 全量崩溃（GBK 冒烟测试当场抓获）**：v0.2.5 自动插桩
  `force_utf8_stdio()` 时，story.py 没有模块层 splib 导入，任何调用都在
  main 第一行 NameError——补 `import splib` 与 scripts 路径
- encoding 纪律说明：本条证明「代码层调用了」≠「实跑可用」，冒烟测试
  （而非仅看代码）是编码纪律的最终验证

### Added
- **全 CLI GBK 冒烟测试**（codex 复审 P2）：fp_extract / ingest / export_pack /
  cost log+report / story sync / names_check 真实实跑并断言关键词
  （"总字符数 / 入库完成 / 已导出 / 已记账 / ok"），timeline_check 走
  --help 路径——不只看返回码，防 errors=replace 把编码错误吞成乱码漏判
- windows-gbk CI job 镜像 ubuntu job 的 validate/export 冒烟（codex 复审 P3.1）

### Changed
- usage.md 编码说明补充 stdin 契约：stdin 亦按 UTF-8 严格解析（当前仅 MCP
  读 stdin），将来新增读 stdin 的 CLI 时宿主需按 UTF-8 输入（codex 复审 P3.2）

## [0.2.5] - 2026-09-29

### Fixed
- **v0.2.4 回归：默认 cp936 下 test_genre 两项报错（codex 复审 P1，已复现）**：
  force_utf8_stdio 让子进程输出 UTF-8，但 test_genre 的 `subprocess(text=True)`
  未指定 encoding，父进程按 locale（cp936）解码 → UnicodeDecodeError →
  stdout=None。5 处全部补 `encoding="utf-8", errors="replace"`
- **编码纪律补全**：v0.2.4 只重配了三个"崩溃点"入口；build_delta / fp_extract /
  export_pack / ingest / cost / story / names_check / timeline_check 在 cp936
  管道输出 GBK 字节，UTF-8 宿主读到乱码——**所有 CLI 入口**统一 force_utf8_stdio

### Changed
- CI 新增 **windows-gbk job**（PYTHONIOENCODING=cp936 跑全量测试）——"默认环境
  健壮"由 CI 持续守护，不再依赖本地环境巧合（codex 复审 P1 建议 2）
- 「接近及格线」措辞修正为"仅供判读留意，不影响判定"（codex 复审 P3.2；
  判定语义本就未变，改措辞消除歧义）
- schema 说明 format_version = pack.json 结构版本，与内容版本 version 无关
  （codex 复审 P3.1：本版变更在 fingerprint.json，pack.json 结构未动，
  format_version "0.1" 保持正确，不升）
- usage.md 编码说明：CLI/MCP 恒为 UTF-8 字节，legacy cp936 交互终端建议
  `chcp 65001` 或 Windows Terminal（codex 复审 P2 采纳文档化变体；拒绝
  ASCII 降级——乱码仅是显示问题且 errors=replace 已防崩，ASCII 化牺牲
  UTF-8 主流场景）

### Measured
- 三环境全绿（47 项）：默认 / 强制 PYTHONIOENCODING=cp936 / cp936 父环境
  跑 GBK·分层·stdio 三套子进程测试

## [0.2.4] - 2026-09-29

### Fixed
- **Windows 默认 GBK 控制台/管道下的编码崩溃（codex 审查 P1，已复现）**：
  validate_pack / fp_check 的 emoji 报告与 MCP 的 ensure_ascii=False JSON 载荷
  在 cp936 流上 UnicodeEncodeError 或被本地代码页污染。三入口（两个 CLI main
  + MCP run_stdio）统一 `force_utf8_stdio()` 重配标准流为 UTF-8（流被宿主
  替换时静默跳过，errors 容错保输出不断流）。旧测试全绿系侥幸——中文可被
  GBK 编码而 emoji 不能
- `build_delta` 普通模式漏写盘的回归（v0.2.3 引入：只在 --layered 分支写文件）
- **pending_aging 字典序错乱（codex 审查 P3）**：章节号 "010" 与 "9" 混排时
  滞留估计失真——chapters_meta 新增 ord 列（文件名数字前缀），按章序排列；
  旧库自动迁移（db 是可重建缓存，schema 不合即删表待 sync 重建）

### Added
- **GBK 环境回归测试**（tests/test_gbk_console.py，3 项）：显式
  PYTHONIOENCODING=cp936 的最恶劣环境下，validate_pack / fp_check 入口不崩、
  MCP stdio 按 UTF-8 字节可解析——把"侥幸绿"变结构性绿，同时补齐
  validate_pack.main / fp_check.main 的入口级覆盖（codex 审查 P2）
- **指纹变更联动 pack.json 升版**：build_delta 比对新旧指纹内容，实际变化才
  patch +1、刷新 updated、changelog 追加重建记录；无变化明确打印"版本不动"
  （codex 审查 P2：两包元数据曾停在 0.1.0 而指纹已分层化，两包已手动对齐 0.2.0）
- 文体判定输出**边界距 margin 连续值**（报告行可见，软化决策留待后续调参）；
  Delta 超及格线 80% 时报告追加"接近及格线，置信降级"（codex 审查 P3 轻量版）
- 统计口径文档化：叠词率仅 AA 型、四字组为非重叠滑窗（style-analyze 与
  fingerprint schema 注明，勿夸大特征覆盖面）

### Changed
- 每版本改动清单移入工作区 `Zcode改动清单及版本/`（自本版起）
- 测试 47 项（+3 GBK 回归）

## [0.2.3] - 2026-09-29

### Added
- **分层指纹（per_genre）**：fingerprint.json 新增 `genres.{narrative,essay}`
  （各层独立阈值树 + Delta 档案）与 `self_check`（层内留一真迹包络）；
  语料阈值容差由**层内各篇实测散布 ×1.2** 推导（固定比例容差会被罕见指标的
  跨篇波动击穿——真迹曾挂自己层线）；稀疏标点不入树防「指标缺失」误杀
- **文体检测器**：双信号（段首引号段占比 + 引号字占比）——嵌入叙述段的对话
  （孔乙己型）靠引号字占比识别；边界附近置信降级为 medium 并如实入报告
- **统一验收路径 layered_check**：fp_check CLI 与 MCP fp.check 共用——auto
  按待测文本文体选层（无层降级混合并明示）、Delta 及格线=层内真迹留一最差篇
  （"至少要像真迹里最不像的那篇"）、短文（<800 字）Delta 只作参考不进判定、
  800–1200 字标"置信中"
- `fp_extract --genre-layers` 分层预览；`build_delta --layered` 一键重建分层指纹；
  validate_pack 对 genres/self_check 施加与顶层同等的阈值纪律
- **evals Case F/G**：分层验收金标准（9 校准点固化，离线可跑）+ 语料扩充重算流程；
  docs/corpus-sources.md 公版源登记表（工具链不内容）

### Fixed
- build_delta_profile 的 std 下限被 `round(…,4)` 归零的潜在除零（仅防零，
  不改既有数值——交叉验证 9/9 保持）
- n=2 层的 Delta 档案是数学退化（任意文本距离恒为 1.0），不再入库，
  运行时回退混合档案作参考值
- 频率语义下「没写=0」：阈值树内缺失路径补 0.0，不再按「指标缺失」判死

### Measured（分层验收矩阵，9 校准点）
- 真迹过线 5/5：秋夜/风筝→luxun essay ✅；孔乙己/故乡/祝福→luxun narrative ✅；
  背影→zhuziqing ✅（混合指纹时代真《秋夜》曾挂 9/12）
- 错作者拒绝 3/3：背影→luxun ❌6/11、匆匆→luxun ❌7/11、秋夜→zhuziqing ❌3/12
- AI 文本落位正确：文1/文2 均不达标，Delta 排序 文2(1.55)<文1(1.67)<真迹(≈1.03)
- 已知限制如实入档：luxun essay 层 n=2 线不可标定；narrative 层留一线偏松
  （小样本方差）；essay 层绝对包络尚不能单独区分作者（指标与 Delta 互补）

### Changed
- **通用性正式化（作者无关）**：新增 schemas/fingerprint.schema.json——分层指纹
  格式契约，genres 层名开放（v0.3 类型包可扩展），全部字段对任意作者语料同构；
  style-analyze 建档流程把 `build_delta --layered` 分层指纹列为标准步骤
  （替换被实测证伪的手拍容差指引）；evals Case H 固化任意作者建档验收模板；
  测试 TestGenericAuthorPipeline 以合成语料走 CLI 全链路，不依赖自带包
- style-check / style-apply / usage.md / MCP fp.check 描述同步分层语义；
  测试 +10（检测器 / 散布容差 / 层内留一 / 统一路径 / CLI 退出码 / 通用性），
  共 44 项

## [0.2.2] - 2026-09-29

### Fixed
- **stylepack.info 三处接口缺陷**（实测"仿鲁迅"暴露，宿主全程未取到包清单）：
  - name 缺省时返回可用包清单（成功路径），不再落入错误路径——"列出包"是
    高频意图，不该走报错
  - 协议层 isError 包装不再丢弃载荷其余字段：此前错误返回里的 `available`
    自救清单被整体替换成一行错误文本，宿主从未收到可用包列表，是误判
    "没有风格包"的直接原因
  - 支持中文名查找：pack.json 的 `display_name`（鲁迅 / 朱自清）作为查找别名，
    与目录名（luxun / zhuziqing）等价
- **writing 前门补三条实测教训**：仓库根定位协议（特征目录法：`stylepacks/` +
  `scripts/` + `core/skills/`，cwd 与仓库根不同层是常态）；取包路径改 MCP 首选
  （stylepack.info 自定位，与 cwd 无关，优先于文件浏览）；失败行为规范——
  未亲眼列出的目录禁止断言"为空 / 不存在"，点名作者套包失败必须上报选项
  （修路径套包写 vs 凭印象直写并声明无验收），禁止静默滑向后者

### Added
- 测试 +1（协议级）：stylepack.info 缺省清单 / 中文别名 / 错误载荷保留 available

### Changed
- stylepack.info 工具描述同步新语义；docs/usage.md MCP 工具表补 stylepack.info 行

## [0.2.1] - 2026-09-29

### Added
- **前门技能 writing**：只路由不写正文的接待员——口语创作请求（随便写写 /
  朋友圈文案 / 续写第三章 / 拆解这本书）从上往下匹配路由表分流到对应技能；
  锚点 + 类别泛化匹配（非穷举），条件默认双向成立（提及自己的章节走项目模式，
  项目目录内说"直接写"走轻模式）；路由落定后读取目标技能 SKILL.md 执行，
  不复述流程；description 含显式排除项（非创作请求不触发）
- **轻模式**：一次性小写作最短路径（≤3 个工具调用）——气质匹配优先于默认包
  （"朋友圈文案"不硬套鲁迅），套包只装 card + 禁用清单（≤1KB），支持单文件包
  直读，跳过拍子确认 / 工作区 / 落库 / 记账
- style-apply 增 **MCP 自动化条款（透明编排）**：连接 MCP 时 story.sync →
  story.recap / story.character 替代直读 bible 与上章结尾，写完
  story.propose_delta 登记、fp.check 快速判定；正式验收留档仍走本地
  fp_check.py（MCP 版暂不带留档与 --baseline 参数）；无 MCP 按原协议读文件，
  两条路径不混用

### Changed
- style-apply description 显式让位：无项目的一次性小写作由 writing 前门承接
- 输出语域规则（意图语言面向用户、工具名只出现在诊断语境）同时写入
  writing 与 style-apply
- docs/usage.md 入口更新：非作者用户从 writing 前门进入；技能表新增 writing 行

## [0.2.0] - 2026-09-28

### Added
- **MCP server**（stdlib 手写 JSON-RPC 2.0 over stdio，最小子集 initialize / tools /
  ping）：10 个工具——story.sync / search / character / recap / foreshadow /
  propose_delta / merge_delta / cost_forecast、stylepack.info、fp.check；
  单次返回 ≤ 2KB、每次调用自动记账（与 cost.py 同账本）
- **记忆层 store.py**：SQLite 状态机（entities / entity_state / pending_deltas /
  chapter_digests / foreshadowing / events / chapters_meta）；
  FTS5 全文检索，缺席自动回退 LIKE；文件仍是权威源（sync 单向导入，可删可重建）
- **Burrows Delta 指纹**：splib 档案构建与距离计算；fp_extract --delta-profile、
  fp_check --delta / --delta-max、build_delta.py；两个自带包已内嵌 Delta 档案
- **双暴露 CLI**：scripts/story.py（sync / search / character / recap / foreshadow /
  propose / merge / aging），与 MCP 工具共用同一实现
- **交叉验证实验**：鲁迅 / 朱自清全部 9 部作品对自包 Delta 距离均小于对方包（9/9）
- 测试 +10：状态机风险分级与合并、MCP 协议握手、交接测试（机械化）、返回纪律、
  真实子进程 stdio 端到端、Delta 分离（合成 + 真实包）

## [0.1.4] - 2026-09-28

### Added
- **落库风险分级**：低风险设定自动合并 + `merged.log` 留痕 + 章末批量摘要；
  中风险批量确认；核心人物变动 / 关键道具 / 伏笔阻断确认——确认成本随风险
  而非数量增长（names.json 新增 `tier` 字段约定）
- **一致性分层体检**：增量模式设为默认（新章 × 影响面实体，不通读全稿），
  全量模式改为卷末 / 每 20–30 章的定期漂移网；报告置顶健康度三行
  （pending 滞留 / 全量距今 / 自动合并复核）
- **注入 lint**：validate_pack 启发式扫描包文件中的指令型语句并警告；
  CONTRIBUTING 增语义安全 review 条款（第三方风格包按第三方代码对待）
- **语料体检**：style-analyze 增多来源交叉验证与离群章节警告，结论进档案元数据
- **盲测制度化**：style-calibrate 每卷必跑，胜率下滑 ≥20 点触发档案复审；
  narrative 包工作流表同步
- **可撤销保底**：style-setup 工作区默认 git init + 首次提交
- style-apply / consistency-check：收尾自检清单（防静默跳步）

### Changed
- v0.2-计划书：工具上限改乘法口径（≤10 元工具 × action ≤5，跨资源不合并）；
  merge_delta 风险分级；指纹 per_genre 分层、跨章趋势检测、盲测为最终裁判
- 版权边界维持既有"仓库不自带全文"纪律，不新增约束（使用侧合规由使用者自负）

## [0.1.3] - 2026-09-28

### Added
- **bible 隔离区**（外部建议采纳）：拍子 / 正文的新设定落 `bible/pending/`，
  经脚本校验（names_check / timeline_check）+ 用户确认两道门后才合并进正式 bible；
  style-setup 工作区模板同步
- fp_check：`--save-metrics` 留档实测指标、`--baseline` 逐指标前后对比，
  「基线通过而本次超差」标记为回归——revise 回滚有了精确的 before/after 数值
- cost.py：`forecast` 子命令——记账历史 × 章节进度预测剩余成本（字符量代理估算，
  明示 ±40% 误差与"生成 token 不可见"口径）

### Changed
- style-apply：写前共创的设定落库改为隔离区仪式；写完验收留档指标；revise 复验引入基线对比
- v0.2-计划书：`apply_delta` 拆分为 `propose_delta` / `merge_delta` 两段式；
  新增 `story.cost_forecast` 工具；新增工具纪律（≤10 上限、描述规范、单一首选路径）

## [0.1.2] - 2026-09-28

### Added
- style-apply：**写前共创**（本章拍子表经用户确认后才生成正文，先干后写防废稿）
  与**局部重写 revise 模式**（按批改报告 P0/P1 定位只改被点名段落，不重写全章）
- 开销预告 + 落账条款写入 style-analyze / style-critique / consistency-check
- `scripts/cost.py`：成本账本（log 记账 / report 出账，落 `<项目>/style/cost.jsonl`）
- `v0.2-计划书.md`：MCP 记忆层设计（故事状态机 + FTS5 RAG + Burrows Delta 指纹）

## [0.1.1] - 2026-09-28

### Changed
- 成本纪律写入技能流程（硬性条款）：style-analyze / style-apply / style-critique /
  consistency-check 强制"同一轮并行批量读取，禁止串行逐个读"；语料 > 100k 字与
  多章批改 / 全篇一致性审查改为子代理 map-reduce（各读一块、各回摘要）
- usage.md 增补「怎么控制 token 成本」FAQ

## [0.1.0] - 2026-09-28

### Added
- 核心脚本（零标准库外依赖）：`ingest`（语料清洗入库）、`fp_extract`（指纹提取）、
  `fp_check`（指纹验收与漂移检测）、`validate_pack`（自包含校验）、`export_pack`
  （单文件导出）、`names_check`（专名一致性）、`timeline_check`（时间线一致性）
- 11 个技能：style-setup / corpus-ingest / style-analyze / style-apply /
  style-critique / style-check / consistency-check / style-feedback /
  stylepack / close-read / style-calibrate
- narrative 类型包结构知识（REFERENCE.md）
- 自带公版风格包：鲁迅（luxun）、朱自清（zhuziqing）——指纹来自真实语料统计
- StylePack 格式 v0.1 定义：pack.json Schema、fingerprint 结构、九章 profile 骨架
- 评估用例（evals/cases.md，Case A–E）与 CI（unittest + 包校验 + 导出冒烟）
- 双语 README、CONTRIBUTING（版权纪律）、docs/usage.md 使用说明与宿主适配文档
