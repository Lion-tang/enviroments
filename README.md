# Enviroments

机房服务器与交换机管理工具。后端使用 FastAPI 提供 API、定时任务、SSH/SFTP/Web SSH 能力；前端使用 Vue 3 + Element Plus；生产模式下后端直接托管前端构建产物。

## 当前能力

- 多用户注册/登录，JWT Bearer Token 鉴权，前端自动携带 Token。
- 服务器管理：添加、编辑、删除、搜索、状态检测、占用/释放、标签、备注、BMC 信息。
- 服务器详情采集：系统版本、CPU 型号/核心数、内存、网卡与 PCI 信息，支持缓存与手动重新采集。
- 每个用户独立收藏服务器，主页可切换“只看收藏”。
- 服务器详情页支持可自由编辑保存的“详情记录”文本框。
- Web SSH：浏览器内终端，基于 WebSocket + xterm.js。
- 文件管理：通过 SFTP 浏览目录、上传、下载，单击目录进入；支持新建目录、拖拽上传文件/目录、上传进度/取消，以及按用户记住每台服务器上次访问目录。
- 交换机管理：交换机 CRUD、SSH 采集 `display version`、关联服务器、详情和日志。
- 日志系统：按服务器/交换机写入 JSON 行日志，前端详情页可查看、刷新和清空。
- Windows EXE 与 Linux tar.gz 打包：GitHub Actions 和本地脚本均可构建。

第一次使用可先阅读 `docs/GETTING_STARTED.md`，按步骤完成注册、添加服务器/交换机、Web SSH 和组网图体验。

## 快速上手

下面流程适合第一次下载代码后，在本机安装依赖、启动开发环境，并一键构建出可运行版本。

### 1. 准备环境

需要先安装：

- Python 3.11 或更新版本
- Node.js 20
- pnpm 10

如果本机还没有 pnpm，可以通过 npm 安装：

```bash
npm install -g pnpm
```

### 2. 下载代码

```bash
git clone https://github.com/xxjunzijun/enviroments.git
cd enviroments
```

### 3. 安装后端依赖

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

Windows PowerShell 可使用：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..
```

### 4. 安装前端依赖

```bash
cd frontend
pnpm install
cd ..
```

### 5. 启动开发环境

开两个终端。

后端：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```bash
cd frontend
pnpm run dev
```

然后打开：

```text
http://localhost:3000
```

### 6. 一键构建出版本

构建前先安装 PyInstaller：

```bash
cd backend
source .venv/bin/activate
pip install pyinstaller
cd ..
```

Linux/macOS：

```bash
chmod +x build.sh
./build.sh
```

Windows：

```bat
build.bat
```

构建成功后，产物会生成到：

```text
dist/Enviroments/
```

运行方式：

```bash
./dist/Enviroments/Enviroments
```

Windows：

```bat
dist\Enviroments\Enviroments.exe
```

运行后打开：

```text
http://127.0.0.1:8000
```

## 项目结构

```text
enviroments/
├─ backend/
│  ├─ app/
│  │  ├─ api/v1/routers/   auth.py files.py logs.py servers.py switches.py terminal.py
│  │  ├─ core/             auth.py database.py scheduler.py
│  │  ├─ models/           server.py server_favorite.py switch.py user.py
│  │  └─ main.py
│  ├─ infrastructure/      ssh_client.py sftp_client.py ssh_worker.py
│  ├─ tests/               webssh_smoke.py
│  ├─ log/                 JSON-line 日志目录
│  ├─ Enviroments.spec     PyInstaller 配置
│  └─ requirements.txt
├─ frontend/
│  ├─ src/
│  │  ├─ api/              index.js
│  │  ├─ components/       ServerDetail.vue SwitchDetail.vue WebTerminal.vue
│  │  ├─ views/            Login.vue ServerList.vue SwitchList.vue
│  │  └─ App.vue
│  ├─ dist/                前端构建产物，由后端静态托管
│  ├─ package.json
│  └─ pnpm-lock.yaml
├─ .github/workflows/      build.yml build-linux.yml build-linux-x86.yml
├─ docs/                   GETTING_STARTED.md README_DEPLOY_LINUX.md
├─ build.bat               Windows 本地打包脚本
├─ build.sh                Linux/macOS 本地打包脚本
└─ README.md
```

## 开发环境启动

### 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

后端地址：`http://127.0.0.1:8000`

### 前端

```bash
cd frontend
pnpm install
pnpm run dev
```

前端开发地址：`http://localhost:3000`

开发模式下，Vite 会把 `/api` 和 `/ws` 代理到 `http://localhost:8000`；Web SSH 使用的 WebSocket 也会经由 `/api` 代理转发到后端。

## 生产构建

### 只构建前端

```bash
cd frontend
pnpm install
pnpm run build
```

构建产物会生成到 `frontend/dist/`。后端启动后会直接托管该目录，因此也可以访问 `http://127.0.0.1:8000` 查看完整页面。

### Windows EXE

先确认已安装 Python、Node.js、pnpm，并且当前 Python 环境已经安装 `backend/requirements.txt` 和 `pyinstaller`：

```bat
cd backend
pip install -r requirements.txt pyinstaller
cd ..
```

然后执行：

```bat
build.bat
```

脚本会执行以下动作：

- 安装/更新前端依赖并构建 `frontend/dist/`。
- 进入 `backend/`，使用 `backend/Enviroments.spec` 打包。
- 输出到根目录 `dist/Enviroments/`。

运行：

```bat
dist\Enviroments\Enviroments.exe
```

### GitHub Actions Linux 离线包

仓库提供 `.github/workflows/build-linux.yml` 和 `.github/workflows/build-linux-x86.yml`，可以让 GitHub 构建 Linux ARM64 或 x86_64 离线部署包。

使用方式：

- 打开 GitHub 仓库的 Actions 页面。
- ARM64 选择 `Build Linux ARM64 Tarball`；x86_64 选择 `Build Linux x86_64 Tarball`。
- 点击 `Run workflow`，可选填写 tag，例如 `v1.0.0`。
- 构建完成后下载 artifact：`Enviroments-linux-arm64-*.tar.gz` 或 `Enviroments-linux-x86_64-*.tar.gz`。
- 将 tar.gz 拷贝到离线 Linux，解压后执行 `./Enviroments`。

详细离线运行说明见 `docs/README_DEPLOY_LINUX.md`。

注意：GitHub 会在 `quay.io/pypa/manylinux_2_34_aarch64` 或 `quay.io/pypa/manylinux_2_34_x86_64` 容器中执行 PyInstaller，因此 Linux 离线包的 glibc 基线为 2.34。低于 glibc 2.34 的离线系统仍需在更老的构建环境中单独构建。

### Linux/macOS 本地打包

```bash
chmod +x build.sh
./build.sh
```

输出目录为 `dist/Enviroments/`。这个脚本会在当前机器架构上打包，适合本机验证或在目标 Linux/macOS 环境中生成对应平台产物；跨平台发布建议使用对应的 GitHub Actions 工作流。

## GitHub Actions 构建

工作流文件：`.github/workflows/build.yml`、`.github/workflows/build-linux.yml` 和 `.github/workflows/build-linux-x86.yml`

Windows EXE 流程：

- 使用 Windows Server 2022。
- 安装 Python 3.11、Node.js 20、pnpm 10。
- `frontend` 下执行 `pnpm install --frozen-lockfile` 和 `pnpm run build`。
- 安装 `backend/requirements.txt` 与 PyInstaller。
- 在 `backend` 目录执行 `pyinstaller Enviroments.spec --noconfirm --clean --distpath ../dist --workpath ../build`。
- 上传 `dist/Enviroments-*` 构建产物。

Linux ARM64 tar.gz 流程：

- 使用 `ubuntu-22.04-arm` runner 负责前端构建，并在 `quay.io/pypa/manylinux_2_34_aarch64` 容器中执行 PyInstaller。
- 安装 Node.js 20、pnpm 10；后端打包容器内使用系统 Python 和 `python3-devel`，保证 PyInstaller 能找到 shared libpython。
- 产物基于 `quay.io/pypa/manylinux_2_34_aarch64`。
- 将 `dist/Enviroments/` 和 `docs/README_DEPLOY_LINUX.md` 打成 `Enviroments-linux-arm64-*.tar.gz`。

Linux x86_64 tar.gz 流程：

- 使用 `ubuntu-22.04` runner 负责前端构建，并在 `quay.io/pypa/manylinux_2_34_x86_64` 容器中执行 PyInstaller。
- 安装 Node.js 20、pnpm 10；后端打包容器内使用系统 Python 和 `python3-devel`，保证 PyInstaller 能找到 shared libpython。
- 产物基于 `quay.io/pypa/manylinux_2_34_x86_64`。
- 将 `dist/Enviroments/` 和 `docs/README_DEPLOY_LINUX.md` 打成 `Enviroments-linux-x86_64-*.tar.gz`。

## 常用检查

```bash
cd frontend
pnpm run build
```

```bash
cd backend
python -m compileall app infrastructure tests
```

```bash
cd backend
python tests/webssh_smoke.py --help
```

`webssh_smoke.py` 是 Web SSH 冒烟测试脚本，需要提供可连接的目标服务器信息后才会真正执行连接测试。

## 数据与日志

- SQLite 数据库默认在 `backend/enviroments.db`。
- 服务器日志在 `backend/log/{server_ip}.log`。
- 交换机日志在 `backend/log/switch_{id}.log`。
- `frontend/dist/`、`backend/enviroments.db`、日志、虚拟环境和依赖目录不应提交到仓库。

## 版本记录

| 版本 | 说明 |
| --- | --- |
| v0.9.x | Web SSH 稳定性修复、终端页面间距优化、xterm 版本兼容调整。 |
| v0.8.x | 服务器收藏、收藏筛选、详情记录、服务器详情抽屉加宽、文件管理单击进入目录。 |
| v0.7.x | 多用户 JWT 认证、服务器占用/释放、BMC 字段、交换机 SSH 采集和 display version 解析。 |
| v0.6.x | 交换机管理、服务器与交换机关联、Tab 切换。 |
| v0.5.x | 详情页缓存、表格列宽优化、Chrome 自动填充修复。 |
| v0.4.x | 备注和 BMC 信息行内编辑。 |
| v0.3.x | CPU 型号、网卡 PCI 信息采集。 |
| v0.2.x | 日志路径修复、标签编辑、搜索栏。 |
| v0.1.x | MVP：服务器管理、文件浏览、SSH 信息采集。 |

## 仓库

https://github.com/xxjunzijun/enviroments

## 第三方代码与致谢

本项目 Web SSH 后端模块参考并改造了 huashengdun/webssh 项目的部分实现：
https://github.com/huashengdun/webssh

原项目采用 MIT License。相关代码已按本项目 FastAPI、WebSocket、Paramiko 架构进行适配。更详细的第三方声明见 `THIRD_PARTY_NOTICES.md`。
