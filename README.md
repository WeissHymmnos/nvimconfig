# nvimconfig (UCDP — Unified Configuration Control Plane for Neovim)

> **愿景 (Vision)**
>
> 这只是一个 Vibe Coding 的 Neovim 配置 GUI 编辑器，我希望类似的配置模式能够抛砖引玉，让 GUI 配置功能覆盖 Linux 系统的全部。

---

## 为什么做这个项目？

在 Linux 与开源工具生态中，大量核心软件（如 Neovim、窗口管理器、终端模拟器、系统服务与各类 Dotfiles）都依赖手写脚本或配置文件。传统的 GUI 配置工具往往试图“直接解析并原地修改源码（基于 AST 字节偏移打补丁）”，一旦遇到条件分支、函数闭包或局部变量引用，就会退化为“只读锁定”甚至破坏用户原有的配置结构。

本项目探索并实现了一种可复用于整个 Linux 配置生态的**双层声明式配置架构（结构化中间态 IR/State + 单向代码生成 Codegen）**：

```text
[GUI 配置器 + Schema]  <──读写──>  [结构化状态文件 (.ucdp/state.json)]  ──单向编译/覆盖生成──>  [最终 Lua 配置文件]
```

1. **首次引导（Bootstrap）**：当配置目录中尚无 `.ucdp/state.json` 时，自动扫描现有的 Neovim Lua 配置（`init.lua`、`lua/**/*.lua`），提取选项（`vim.opt` / `vim.g` / `vim.env`）、快捷键（`vim.keymap.set`）与插件声明（`lazy.nvim` / `packer.nvim` / `vim-plug`），初始化生成结构化状态文件。
2. **结构化读写（Single Source of Truth）**：GUI 的所有增删改查直接作用于结构化的 `.ucdp/state.json`，不再受制于原文件 AST 槽位是否已存在，彻底消除“未写入字段无法点击修改”的痛点。
3. **确定性单向代码生成（Codegen）**：每次状态更新后，编译器自动将 `.ucdp/state.json` 单向编译为干净、规范的 Lua 源码文件，并通过 Msgpack-RPC 实时同步给正在运行的 Neovim 实例。

如果将这一“**Schema 驱动 GUI + 结构化中间态 State + 确定性配置生成**”范式推广开来，Linux 下的各种复杂文本配置都能拥有统一、直观、永不写坏源码的现代化图形配置体验。

---

## 功能特性

- **双层架构后端 (`ucdp-daemon`, Rust)**
  - 基于 `full_moon` 的 Lua AST 首次迁移引导与确定性代码生成。
  - `.ucdp/state.json` 结构化状态持久化与原子写入。
  - 基于 HTTP + SSE 的实时状态同步流与乐观锁冲突检测。
  - 通过 Unix Socket / Msgpack-RPC 与活动 Neovim 实例进行实时热更新。
- **Material Design 3 桌面界面 (`qt_gui/`, PyQt6)**
  - 严格遵循 Material Design 3 色彩系统（支持 Material You 深色/浅色、Tokyo Night、Catppuccin Mocha、Gruvbox Dark、Nord 等主题）与全局无级缩放。
  - 纯矢量 `QPainter` 几何图标渲染，零 Emoji 依赖。
  - **常用设置与全部原生选项**：根据 Neovim 选项 Schema 自动渲染开关、滑块、枚举下拉框与结构化表编辑器。
  - **快捷键管理**：按模式（Normal / Insert / Visual / Terminal）过滤、内联新增、修改与删除快捷键映射。
  - **插件主从检查器（Master-Detail Split View）**：左侧插件列表 + 右侧四标签页结构化检查器（参数与状态、按需触发、版本与构建、实时 Spec 代码预览），支持 `lazy.nvim`、`packer.nvim` 与 `vim-plug`。

---

## 目录结构

```text
.
├── src/                  # Rust 守护进程源码 (AST 解析、State 管理、Lua 代码生成、HTTP/SSE 服务)
├── qt_gui/               # PyQt6 Material Design 3 图形配置界面
│   ├── main.py           # 主窗口、导航抽屉、分类页面与实时状态同步
│   ├── widgets.py        # MD3 组件库、插件主从检查器、快捷键卡片、Lua 结构化编辑器
│   ├── theme.py          # MD3 语义化调色板与全局 QSS 样式引擎
│   └── client.py         # 异步 HTTP 与 SSE 客户端
├── plugin/ucdp-bridge.lua # Neovim 插件入口 (:NvimGuiSettings 命令注册)
├── lua/ucdp_bridge/       # Neovim 端桥接模块
└── tests/                # Python 前端渲染、状态同步与边界对抗测试套件
```

---

## 快速开始

### 1. 环境依赖

- **Rust 工具链**（`cargo`）
- **Python 3.10+** 及 **PyQt6**（`pip install PyQt6`）
- **Neovim 0.9+**

### 2. 编译守护进程

```bash
cargo build --release
```

### 3. 启动配置器

可以直接在 Neovim 中通过插件命令启动：

```vim
:NvimGuiSettings
```

或手动启动守护进程与 GUI：

```bash
# 启动守护进程（默认读取 ~/.config/nvim/init.lua，输出 JSON 格式连接信息）
./target/release/ucdp-daemon

# 使用输出的 http 地址与 token 启动 GUI
python3 qt_gui/main.py --url <http_url> --token <token>
```

### 4. 运行测试

```bash
# 运行 Rust 单元测试
cargo test

# 运行 PyQt6 离屏渲染与对抗测试
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```
