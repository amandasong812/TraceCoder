# TraceCoder

TraceCoder 是一个基于 Ollama 的本地可视化编程智能体。它将编程任务拆解为结构化计划节点，在后端校验并执行工具调用，同时记录文件读取、文件修改、命令输出和最终结果，方便用户查看完整执行过程。

## 功能特性

- 使用本地 Ollama 模型完成任务规划和代码修改决策。
- 以结构化 action 驱动执行流程，支持 `plan`、`tool`、`final` 三类动作。
- 使用计划图记录节点状态：`pending`、`running`、`success`、`failed`、`revised`。
- 提供工作区沙箱，限制文件访问范围并拒绝路径穿越。
- 内置文件工具：列出文件、读取文件、写入文件。
- 内置命令工具：在允许列表内执行本地命令并记录输出。
- 保存 trace 记录，将 observation、命令结果和文件变更绑定到计划节点。
- 提供 FastAPI 后端接口和 Server-Sent Events 事件流。
- 提供 React/Vite 前端，用于提交任务、查看计划 timeline、工具输出和最终报告。
- 包含一个带测试失败样例的 `demo_project`，可用于演示修复流程。

## 项目结构

```text
TraceCoder/
├── backend/        # FastAPI 后端、agent loop、工具系统和 trace 存储
├── frontend/       # React/Vite 前端界面
├── demo_project/   # 演示用的 Python 项目
└── README.md
```

## 环境要求

- Python 3.10+
- Node.js 18+
- Ollama

建议提前准备一个代码模型，例如：

```powershell
ollama pull qwen2.5-coder:7b
```

如果本地没有该模型，后端会尝试从已安装模型中自动选择可用模型。

## 启动后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

常用环境变量：

- `TRACECODER_WORKSPACE`：允许智能体访问和修改的工作区，默认是仓库根目录。
- `TRACECODER_MODEL`：指定 Ollama 模型名，未设置时自动选择已安装模型。
- `OLLAMA_BASE_URL`：Ollama 服务地址，默认是 `http://localhost:11434`。
- `TRACECODER_MAX_STEPS`：单次任务最大循环步数，默认是 `12`。

可访问以下接口检查后端状态：

```text
GET /api/health
GET /api/ollama
GET /api/tools
```

## 启动前端

```powershell
cd frontend
npm install
npm run dev
```

启动后打开 Vite 输出的本地地址，在页面中输入任务并开始运行。

## 演示任务

可以使用内置的 `demo_project` 验证基础流程：

```text
修复 demo_project 中失败的测试。请先阅读相关文件，运行测试，定位问题，做最小修改，然后再次运行测试。
```

该样例包含一个故意写错的 `subtract` 函数，适合展示读取文件、执行测试、修改代码和复测的完整 trace。
