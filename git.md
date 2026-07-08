# Git 基础概念

## 1. 核心概念

### Git 是什么

分布式版本控制系统。每个开发者本地都有**完整的仓库副本**，不依赖中央服务器也能工作。

### 三层结构

```
工作目录 (Working Directory)          暂存区 (Staging Area)           仓库 (Repository)
   你编辑的文件           ──git add──→   准备提交的文件     ──git commit──→   永久快照
       ↑                                    ↑                                ↑
   看得见摸得着                         "购物车"                          .git/ 目录里
```

| 层 | 位置 | 作用 |
|----|------|------|
| 工作目录 | 你看到的项目文件夹 | 编辑、增删文件 |
| 暂存区 | `.git/index` | 选择哪些改动要放进下一次 commit |
| 仓库 | `.git/objects` | 永久存储所有 commit 快照 |

### `.git` 目录

项目根目录下的隐藏文件夹，Git 的全部数据都存在里面。删掉 `.git` = 删掉所有版本历史，只剩当前文件。

---

## 2. Commit

### commit 是什么

把**暂存区**的内容保存为一个永久快照（snapshot）。

### commit 记录了

```
Commit a1b2c3d
  ├── 父 commit: e5f6g7h        ← 上一个 commit 的 ID，构成历史链
  ├── 作者 + 时间
  ├── 提交信息 (commit message)
  └── 文件快照（整个项目此刻的状态）
```

### commit 不记录什么

- ❌ 在哪个分支上创建的 — commit 不知道也无需知道
- ❌ 谁 push 的 — 那是远程仓库记录的

### 本地 vs 远程

```
git commit  →  只写入本地 .git 目录，和 GitHub 无关
git push    →  把本地 commit 同步到 GitHub
```

---

## 3. 分支

### 分支是什么

分支只是一个**指向某个 commit 的指针**，不是一个实体。创建分支 = 创建一个新指针，开销几乎为零。

```
                          master
                            ↓
A ──→ B ──→ C ──→ D
                  ↑
            feat/login
```

### 分支操作

```bash
git branch                     # 列出所有本地分支
git branch <name>              # 创建分支（不切换）
git checkout <name>            # 切换到已有分支
git checkout -b <name>         # 创建并切换
git branch -d <name>           # 删除分支（安全，未合并会警告）
git branch -D <name>           # 强制删除
```

### 分支与 commit 的关系

同一个 commit 可以被多个分支指向：

```
master ──→ C ←── feat/login        # 刚从 master 创建分支时，两者指向同一个 commit

# 随着各自 commit，分支分叉：
master ──→ E ←── feat/login        # 不是这样
master ──→ D                       # 而是这样，master 不动
C ──→ E                            # login 分支多了 E
```

commit 本身通过父指针形成链，分支只是"从哪里开始读历史"的入口。

---

## 4. HEAD

### HEAD 是什么

指向你**当前所在位置**的指针。它不是 commit，它是一个引用。

### 两种状态

```
正常状态 (attached)：
  HEAD → master → commit C          HEAD 指向一个分支

游离状态 (detached HEAD)：
  HEAD → commit C                    HEAD 直接指向一个 commit
                                     （不属于任何分支，做实验用的临时状态）
```

### 常用写法

| 写法 | 含义 |
|------|------|
| `HEAD` | 当前所在 commit |
| `HEAD~1` | 上一个 commit（父 commit） |
| `HEAD~3` | 往前第 3 个 commit |
| `HEAD@{upstream}` | 当前分支关联的远程分支 |

---

## 5. Origin & Remote

### origin

`origin` 是远程仓库的**简称**（URL 别名）。克隆时 Git 自动创建。

```bash
git remote -v        # 查看远程仓库地址
# origin  https://github.com/user/repo.git (fetch)
# origin  https://github.com/user/repo.git (push)
```

### origin/master

**不是真正的远程分支**。它是远程 `master` 在你本地的**缓存快照**，只读。

```
GitHub 上                              你本地
  master (真·远程分支)      origin/master (本地缓存的只读副本)
                                   ↑
                           git fetch 时更新

                           master (你工作的本地分支，可写)
```

### fetch vs pull

```bash
git fetch origin          # 只下载远程更新到 origin/master，不影响你的分支
git merge origin/master   # 把 origin/master 合并到当前分支
git pull                  # = fetch + merge，二合一
```

建议新手先用 `fetch` + `merge`，搞清楚两步分别发生了什么。

---

## 6. Push & Pull

### push

把本地分支的 commit 推送到远程对应分支。

```bash
git push origin master              # 推 master
git push origin feat/langfuse       # 推 feature 分支
```

- push 是**追加**，不是覆盖（前提是远程没有别人先推了新 commit）
- 如果别人已经推了，Git 会**拒绝**，需要先 pull
- push 后远程分支和本地分支完全一致

### pull

从远程拉取更新并合并到本地。

```bash
git pull origin master    # 拉取远程 master → 合并到本地当前分支
```

### 冲突

当 pull 或 merge 时，两个分支改了同一行，Git 无法自动合并 → 需要手动解决冲突。

---

## 7. PR (Pull Request)

### 是什么

PR 是 GitHub 的概念：**请求将你的分支合并到另一个分支**。

```
PR: feat/login → master
         │
         ├── 创建 PR  →  GitHub 上展示 diff
         ├── Review   →  团队查看、评论、讨论
         ├── 修改     →  可以继续 push 到分支，PR 自动更新
         └── Merge    →  通过后，代码正式合入目标分支
```

### PR vs Push

| 操作 | 方向 | 需要审核 |
|------|------|----------|
| `git push` | 本地分支 → 同名远程分支 | ❌ |
| PR | 功能分支 → 主分支 | ✅ |

### 注意

- PR 不是 merge — 创建 PR 只是发起请求，合并需要手动确认
- 不同平台叫法不同：GitHub 叫 Pull Request，GitLab 叫 Merge Request
- PR 合并后，功能分支可以安全删除

---

## 8. Worktree

### Git worktree

Git 内置功能，允许同一个仓库有**多个工作目录**，各自在不同的分支上。

```bash
git worktree add ../feature-branch feature-branch   # 在新目录 checkout feature-branch
git worktree list                                    # 列出所有 worktree
git worktree remove ../feature-branch                # 正确删除 worktree
git worktree prune                                   # 清理已失效的 worktree 引用
```

### Claude Code 对 worktree 的使用

Claude Code 在 Git worktree 之上封装了一层，用于隔离并行会话：

```
Claude Code 创建:
  git worktree add .claude/worktrees/<random-name> -b claude-<random>
     ↓
  新目录 + 新本地分支，独立于主工作区

会话结束后:
  无改动 → 自动删除 worktree + 分支
  有改动 → 提示 keep 或 remove
```

- 手动删目录不等于 `git worktree remove` — 需要用 `git worktree prune` 清理残留
- `worktree.baseRef: "fresh"` 从远程默认分支创建，`"head"` 从当前 HEAD 创建
- Claude Code **不会**自动 merge worktree 分支

---

## 9. 常用命令速查

| 命令 | 作用 |
|------|------|
| `git status` | 查看工作区状态（改了哪些文件） |
| `git diff` | 查看未暂存的改动 |
| `git diff --staged` | 查看已暂存（git add 后）的改动 |
| `git log --oneline` | 查看 commit 历史 |
| `git add <file>` | 将文件加入暂存区 |
| `git add .` | 暂存所有改动 |
| `git commit -m "msg"` | 提交暂存区内容 |
| `git push origin <branch>` | 推送到远程 |
| `git pull origin <branch>` | 从远程拉取并合并 |
| `git fetch origin` | 下载远程更新（不合并） |
| `git checkout <branch>` | 切换分支 |
| `git checkout -b <branch>` | 创建并切换分支 |
| `git merge <branch>` | 将指定分支合并到当前分支 |
| `git branch` | 列出本地分支 |
| `git branch -d <branch>` | 删除分支 |
| `git remote -v` | 查看远程仓库 URL |
| `git stash` | 暂存当前改动（临时搁置） |
| `git clone <url>` | 克隆远程仓库到本地 |

---

## 10. 典型工作流

### 日常开发

```bash
# 1. 从 master 创建功能分支
git checkout master
git pull origin master              # 确保是最新的
git checkout -b feat/my-feature

# 2. 开发 + 提交
# ... 写代码 ...
git add .
git commit -m "feat: add my feature"

# 3. 推送到 GitHub
git push origin feat/my-feature

# 4. 创建 PR（在 GitHub 网页上操作）
# feat/my-feature → master

# 5. Review 通过，在 GitHub 点 Merge

# 6. 清理
git checkout master
git pull origin master              # 拉取合并后的最新代码
git branch -d feat/my-feature       # 删除本地分支
```

### Fork 流程（贡献开源项目）

```
原仓库 (upstream)  →  Fork 到你的账号 (origin)  →  clone 到本地
                                                      ↓
                                                PR: 你的 fork → 原仓库
```

### 一次 push 到多个远程

```bash
git remote add origin2 <另一个URL>
git push origin master
git push origin2 master
```
