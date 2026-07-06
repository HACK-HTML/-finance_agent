# Claude Code Context Window 原子内容分类

> Session 启动时，Plugin 和手动添加的 MCP 都被拆解为原子内容进入 Context Window，不保留来源标签。

---

## Context Window 八大类别

```
Context Window
│
├── ① System Prompt（系统提示词）
│     ├── 行为指令（how to behave）
│     ├── 内置工具完整 schema（39 个 Tool 的定义）
│     └── Output Style（如果有设置）
│
├── ② CLAUDE.md（项目指令）
│     ├── managed 层  →  C:\Program Files\ClaudeCode\CLAUDE.md
│     ├── user 层     →  ~\.claude\CLAUDE.md
│     ├── project 层  →  .\CLAUDE.md
│     └── local 层    →  .\CLAUDE.local.md
│
├── ③ Memory（自动记忆）
│     └── MEMORY.md + 各个 topic 文件（.md）
│
├── ④ Rules（规则文件）
│     └── .claude/rules/*.md（可按路径/文件类型条件加载）
│
├── ⑤ Tool 名字（工具目录）
│     ├── 内置 Tool（完整 schema，已加载）
│     ├── MCP Tool 名字（schema 延迟到 ToolSearch 加载）
│     └── MCP Tool 名字（plugin 来源，同上）
│
├── ⑥ Skill 描述（技能目录）
│     ├── bundled skill 描述
│     ├── user/project/plugin skill 描述
│     └── （完整 SKILL.md 正文延迟到触发时加载）
│
├── ⑦ 环境信息
│     ├── 当前日期
│     ├── 工作目录路径
│     ├── Git 状态（分支、改动文件列表）
│     ├── 操作系统 / Shell
│     └── 权限模式
│
└── ⑧ 对话消息（Messages）
      ├── 用户消息
      ├── Claude 回复
      ├── Tool 调用及结果
      └── 系统通知（compaction 摘要等）
```

---

## 按加载时机分类

| 类别 | 启动时加载（常驻 token） | 按需加载（临时占 token） |
|------|:--:|:--:|
| System Prompt | ✅ 全量 | — |
| CLAUDE.md | ✅ 全量 | — |
| Memory | ✅ MEMORY.md 索引 | ✅ topic 文件正文 |
| Rules | ✅ 无路径条件的 | ✅ 有路径条件的（按文件触发） |
| Tool 名字 | ✅ 名字列表 | ✅ MCP 完整 schema（ToolSearch） |
| Skill 描述 | ✅ 名字 + 描述 | ✅ SKILL.md 正文（触发时） |
| 环境信息 | ✅ 全量 | — |
| 对话消息 | — | ✅ 随对话增长 |

---

## Plugin / 手动 MCP 拆解对照

```
手动 MCP (claude mcp add) ────┐
                               │
Plugin 自带的 MCP (.mcp.json) ─┤
                               │
Plugin 自带的 skills/ ─────────┤  拆解为原子内容 ──► Context Window
                               │
Plugin 自带的 agents/ ─────────┤
                               │
Plugin 自带的 hooks/ ──────────┘  (hooks 外部执行，不进 Context Window)
```

| 拆解产物 | 进入 Context Window | 说明 |
|----------|:--:|------|
| MCP tools/list → 工具名列表 | ✅ ⑤ | 仅名字，完整 schema 延迟到 ToolSearch |
| MCP resources/list → 资源列表 | ✅ 按需 | 通过 ListMcpResourcesTool 查询 |
| MCP prompts/list → prompt 模板 | ✅ 按需 | 通过 Skill 工具加载 |
| Plugin skills/SKILL.md → skill 描述 | ✅ ⑥ | 名字+描述，正文延迟 |
| Plugin agents/*.md → agent 描述 | ✅ subagent 时 | 仅 spawn 时加载到子 context |
| Plugin hooks/hooks.json → hooks | ❌ | 外部执行，零 context 占用 |
| Plugin 本身 | ❌ | 打包容器，不进 context |
| MCP Server 本身 | ❌ | 连接通道，不进 context |

---

## 不按来源归类，按类型归类

Context Window 里的内容是扁平化的——Claude 不知道也不需要知道某个 tool 来自哪个 plugin：

```
Context Window

  📦 Tools（按类型：内置 / MCP）
     ├── Read, Write, Edit, Bash, Agent, ...
     ├── mcp__claude-code-docs__search_...        ← 手动 MCP
     └── mcp__plugin_github_github__list_...      ← Plugin MCP

  📦 Skills（按类型：bundled / user / project / plugin）
     ├── /code-review       ← bundled
     ├── /commit-commands:commit  ← plugin
     └── /my-custom-skill   ← project

  📦 CLAUDE.md（按层级：managed / user / project / local）

  📦 Memory（项目记忆文件）

  📦 Messages（对话历史）
```

---

## Session 启动完整加载流程

```
claude 启动
    │
    ▼
① 读取配置文件
   ~/.claude/settings.json     (user scope)
   .claude/settings.json       (project scope)
   .claude/settings.local.json (local scope)
   .mcp.json                   (项目 MCP)
   ~/.claude.json              (user/local scope MCP)
    │
    ▼
② 加载 Plugin
   读 ~/.claude/plugins/cache/<plugin>/
     → .mcp.json 或 plugin.json 中的 mcpServers
     → skills/  → SKILL.md
     → hooks/   → hooks.json
     → agents/  → agent 定义
   Plugin MCP 和手动 MCP 合并
    │
    ▼
③ 连接 MCP Server
   每个 server 发送 MCP 协议请求:
     → tools/list     (获取工具列表 + JSON Schema)
     → resources/list (获取资源列表)
     → prompts/list   (获取 prompt 模板)
   Claude Code 完整存储所有 schema（在内存中，不进 context）
    │
    ▼
④ 构建 Context Window
   ✅ CLAUDE.md              ← 全文注入（Messages 层）
   ✅ Skill 描述             ← 仅名字+描述
   ✅ MCP 工具名             ← 仅名字（Tool Search 模式）
   ✅ 内置工具               ← 完整 schema（System Prompt 层）
   ✅ 环境信息               ← 日期/OS/Git 状态
   ❌ MCP 工具完整 schema    ← 延迟到 ToolSearch 调用时注入
   ❌ Skill 完整内容          ← 延迟到 /skill 或自动触发时注入
    │
    ▼
⑤ 会话就绪
   Claude 看到:
     39 个内置工具 (完整可用)
     MCP 工具名列表 (知道有什么，schema 待查)
     Skill 描述列表 (知道有什么技能可用)
     CLAUDE.md 全文
```

---

## 关键概念对照

| 概念 | 进入 Context Window? | 作用 |
|------|:--:|------|
| Plugin | ❌ | 打包容器，分发单位 |
| MCP Server | ❌ | 连接通道，管理 tool 生命周期 |
| MCP Tool 名字 | ✅ (⑤) | 轻量索引，每个占 ~30 token |
| MCP Tool 完整 schema | ✅ 按需 | ToolSearch 调用后临时注入 |
| Skill 描述 | ✅ (⑥) | 名字+一句话描述，每个 ~50 token |
| Skill 正文 (SKILL.md) | ✅ 按需 | 触发后注入，用完可 compact |
| Hook | ❌ | 外部执行脚本，零 context 成本 |
| Agent 定义 | ✅ subagent 时 | 仅在 spawn 子 agent 时加载 |
| CLAUDE.md | ✅ (②) | 全文常驻 |
| Memory | ✅ (③) | MEMORY.md 索引常驻，topic 按需 |

---

## Slash Commands（`/` 命令）完整参考

> 键入 `/` 列出所有可用命令。命令仅在消息开头时识别，后跟文本作为参数传入。
> 命令按**来源**分为三大类：Built-in（硬编码在 CLI）、Skill（bundled skill，等同于用户自写的 skill）、Workflow（bundled 动态工作流）。
> 可用性因平台、计划和环境而异。

### 按场景分类

```
项目初始化
  /init           → 生成 CLAUDE.md 骨架
  /memory         → 编辑 CLAUDE.md / 自动记忆
  /mcp            → 管理 MCP server 连接和 OAuth 认证
  /agents         → 管理 subagent 配置
  /permissions    → 管理工具权限规则（别名 /allowed-tools）
  /hooks          → 查看 hook 配置
  /ide            → IDE 集成管理

会话控制
  /clear [name]   → 清空对话，新建上下文（别名 /reset, /new）
  /compact [ins]  → 压缩对话为摘要，释放 context
  /context [all]  → 可视化 context 占用（彩色网格）
  /btw <question> → 快速旁提问，不写入对话历史
  /rename [name]  → 重命名当前 session
  /resume [sess]  → 恢复历史 session（别名 /continue）
  /branch [name]  → 分叉当前对话，保持原对话可恢复
  /fork <指令>    → 派生子 agent 继承对话，后台执行后返回结果
  /background [p] → 整个 session 转入后台（别名 /bg）
  /cd <path>      → 切换工作目录（v2.1.169+）
  /add-dir <path> → 添加额外文件访问目录
  /goal [条件]    → 设目标，Claude 跨 turn 自动执行直到满足
  /exit           → 退出（别名 /quit）。后台 session 中仅 detach
  /recap          → 生成当前 session 一句话摘要
  /export [file]  → 导出对话为纯文本

并行工作
  /tasks          → 列出当前 session 的后台任务
  /agents         → 打开 subagent 管理器（Running + Library）
  /batch <指令>   → [Skill] 大规模代码变更，分解为 5-30 个独立单元并行执行
  /workflows      → 管理工作流

模型与推理调整
  /model [model]  → 切换模型并保存为默认
  /effort [level] → 调整推理力度：low/medium/high/xhigh/max/ultracode/auto
  /advisor [m|off]→ 启用/禁用 advisor tool（第二模型辅助）（v2.1.98+）
  /fast [on|off]  → 切换 fast mode

配置与调试
  /config [k=v]   → 打开设置面板/直接设值（别名 /settings）
  /theme          → 设置主题
  /doctor         → 诊断安装和配置问题
  /debug [描述]   → [Skill] 开启 debug 日志并排查问题
  /feedback [r]   → 提交反馈/报告 bug（别名 /bug, /share）
  /doctor         → 诊断安装/配置，f 键自动修复

提交前检查
  /diff           → 交互式 diff 查看器
  /code-review [effort] [--fix] [--comment] [target]
                  → [Skill] 代码审查 correctness bugs + 简化/效率建议
  /review [PR]    → 对 GitHub PR 做只读审查
  /security-review → 更深度的只读安全检查
  /simplify       → 仅做清理优化，不查 bug（v2.1.154+）

回退与恢复
  /rewind         → 回退对话/代码到之前检查点（别名 /checkpoint, /undo）
  /resume [sess]  → 恢复历史 session

其他
  /help           → 显示帮助
  /login          → 登录 Anthropic 账号
  /logout         → 登出
  /color          → 设置提示栏颜色
  /copy [N]       → 复制最后回复到剪贴板
  /cost           → 别名，同 /usage
  /usage          → 查看用量/费用
  /keybindings    → 打开键盘快捷键文件
  /plan [描述]    → 从 prompt 直接进入 plan 模式
  /sandbox        → 切换沙盒模式
  /vim            → 切换 vim 编辑模式
  /terminal-setup → 终端设置
  /schedule [描述]→ 创建/管理云端定时任务（别名 /routines）
  /release-notes  → 查看 changelog
  /reload-plugins [--force] → 不重启重载插件
  /reload-skills  → 不重启重新扫描 skill 目录（v2.1.152+）
  /plugin [sub]   → 管理插件：list/install/enable/disable
  /desktop        → 转到 Desktop App 继续（别名 /app）
  /mobile         → 显示移动端下载二维码（别名 /ios, /android）
  /chrome         → 配置 Chrome 扩展
  /radio          → 打开 Claude FM lo-fi 电台
  /powerup        → 互动式功能学习
  /install-github-app → 为仓库安装 Claude GitHub App
  /install-slack-app → 安装 Claude Slack App
  /insights       → 生成 session 分析报告
  /passes         → 分享免费一周 Claude Code
  /privacy-settings → 隐私设置
  /remote-control → 允许从 claude.ai 远程控制（别名 /rc）
  /remote-env     → 配置云端 agent 默认环境
  /fewer-permission-prompts → [Skill] 扫描 transcript 自动生成 allowlist
  /deep-research <question> → [Workflow] 多源搜索 + 交叉验证 + 合成报告
  /claude-api [migrate|managed-agents-onboard]
                  → [Skill] 加载 Claude API 参考 / 升级旧代码 / 创建 Managed Agent
  /run            → [Skill] 启动并驱动项目 app，验证改动（v2.1.145+）
  /run-skill-generator → [Skill] 教 /run 和 /verify 如何构建/启动项目（v2.1.145+）
  /verify         → [Skill] 运行项目 app 验证改动（v2.1.145+）
  /autofix-pr [p] → 在云端 watch PR，CI 失败或有 review 时自动推送修复
  /teleport       → 将 web session 拉到终端
  /scroll-speed   → 调节鼠标滚轮速度（仅 fullscreen）
  /heapdump       → 导出 JS 堆快照用于内存诊断
  /loop [interval] [prompt]
                  → [Skill] 反复执行 prompt（别名 /proactive）
  /pr-comments    → （v2.1.91 已移除，直接让 Claude 查看 PR 评论）

### 来源类型标记

| 标记 | 含义 |
|------|------|
| **[Skill]** | Bundled Skill：等同于用户自定义 skill，Claude 可自动触发 |
| **[Workflow]** | Bundled 动态 Workflow：fan-out 多 subagent 后台运行 |
| 无标记 | Built-in 命令：行为硬编码在 CLI 中 |

### 快捷对照（高频命令）

| 命令 | 一句话 |
|------|--------|
| `/clear` | 清空对话，开新上下文 |
| `/compact` | 压缩对话为摘要 |
| `/context` | 查看 context 占用 |
| `/model` | 切换模型 |
| `/effort` | 调整推理深度 |
| `/permissions` | 管理权限规则 |
| `/mcp` | 管理 MCP 连接 |
| `/init` | 初始化项目 CLAUDE.md |
| `/diff` | 查看改动 |
| `/code-review` | 代码审查 |
| `/rewind` | 回退到之前检查点 |
| `/resume` | 恢复历史对话 |
| `/help` | 帮助 |
