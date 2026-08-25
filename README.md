# Skills

个人 Codex Skill 集合。

## D2A

`d2a` 是一个项目本地架构实验室，用于：

- 按阶段拆解真实代码架构；
- 生成 S99 代码地图与证据；
- 进行架构质疑；
- 构建和测试最小可运行 Mini；
- 在项目中生成可恢复的 `.d2a` 工作区与本地报告。

### 安装

```bash
git clone https://github.com/sfenga/skills.git
mkdir -p ~/.codex/skills
cp -R skills/d2a ~/.codex/skills/d2a
```

### 使用

在 Codex 中进入目标项目，然后显式调用：

```text
$d2a 初始化当前项目
```

该 Skill 只会在目标项目的 `.d2a` 目录中生成工作产物。
