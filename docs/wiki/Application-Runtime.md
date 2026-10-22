# 用 EduClaw 构建独立应用

## 设计决策

采用 **小内核、可选能力插件、应用自己的组合入口**。EduClaw 工作台是产品；`educlaw-runtime` 是可嵌入其他产品的后端库。应用可以直接导入 SDK，也可以把相同运行时放在 HTTP 服务后面。运行应用不需要先启动工作台，界面可由 React、Vue、桌面框架、移动端或应用原有后端提供。

参考 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的插件组合思路，借鉴其可替换能力与生命周期，不引入 Cordis/TypeScript 作为现有 Python 后端的强制依赖。数据所有权、能力检查和运行记录保留在内核，业务与模型适配留给应用作者。

```text
应用自己的界面 / CLI / 后端
  └─ Python SDK 或可选 HTTP 接口
      └─ Application（每个应用一个实例）
          ├─ 内核：配置、生命周期、能力检查、运行事件
          ├─ chat：模型适配器 + 允许的工具
          ├─ memory / knowledge / skills：可选上下文
          ├─ 业务插件：自定义 API、工具、业务存储
          └─ 应用自己的数据目录
              ├─ agent/：会话、运行、事件
              ├─ plugins/：插件数据
              └─ business/：业务数据库和文件

EduClaw 工作台 → 平台自己的数据目录
独立应用 B    → 应用 B 自己的数据目录
```

## 已实现的范围

| 部分 | 能力 | 关闭后的行为 |
| --- | --- | --- |
| 内核 | 应用数据归属、进程锁、生命周期、请求幂等、事件记录 | 不可绕过的基础能力 |
| chat | 会话、持久历史、有界模型/工具循环、失败与中断状态 | 所有聊天接口不可用 |
| memory | 当前会话近期 4 轮、较早记录 BM25 召回 | 历史继续保存，但不再发送给模型 |
| knowledge | 文本资料导入、按会话挂载、本地 BM25 检索 | 资料接口关闭且不再注入模型 |
| skills | 从应用显式指定的目录浏览、读取、选择 Skill | 接口和指导注入关闭 |
| tools | 应用显式白名单内的已注册工具 | 不暴露工具规格，也拒绝模型调用 |
| 自定义插件 | 注册业务 API、模型工具、上下文提供器 | 注销对应 API、工具和上下文 |
| HTTP | 本机 JSON API、Bearer token、显式 CORS 来源 | 不启动 HTTP 时仍可直接使用 SDK |

现有 `StateManager` 会话/运行/事件记录、检索分块与 BM25、SkillRegistry 的实现提取到 `educlaw._shared`，旧导入路径保留兼容转发，工作台与 SDK 使用同一份实现。wheel 只导出 `educlaw` 命名空间，不把容易与应用冲突的 `core` 包安装进环境。没有复制用户数据。SDK 不导入旧工作台服务、MCP 启动器、全局模型工厂或平台 `.env`。

这是新的可用 SDK 边界，**不代表旧工作台全部模块已经迁移成插件**。旧任务规划/审批、MCP、终端、专家模式、混合语义模型和 GUI 暂时沿用原入口。它们没有作为不完整的开关暴露在独立应用中，也不应直接把旧全局服务包装进插件。后续接入要先显式注入存储、权限与进程环境，再运行隔离测试。SDK 的 memory/knowledge 当前采用本地关键词检索，不承诺工作台全部检索能力。

## 安装与创建

运行时要求 Python 3.11+，基础 SDK 没有第三方运行依赖。可用 Conda、venv 或应用既有环境。构建 wheel 需要 setuptools 68+ 与 wheel；这些是构建工具，不是 SDK 运行依赖。当前未向 PyPI 发布，请从开发分支构建安装。

```powershell
# 在 EduClaw 源码目录构建 wheel
python -m pip install "setuptools>=68" wheel
python -m pip wheel . --no-deps --no-build-isolation -w dist

# 在应用自己的环境安装；无需平台源目录
python -m pip install C:\path\educlaw_runtime-0.1.0-py3-none-any.whl

# 新目录，拒绝覆盖现有应用
python -m educlaw init D:\apps\research-helper --id research-helper --plugins chat,memory,knowledge,skills
python D:\apps\research-helper\main.py
```

`init` 生成 `app.toml`、独立入口、Skills 目录及说明。默认模型是明确标注的离线回声，仅用于检查安装；连接真实模型后才有 LLM 能力。[独立笔记应用源码](https://github.com/weiyu687/EduClaw/tree/codex/roadmap-development/examples/standalone-agent)展示业务 API 与只读 agent 工具的组合。

## 配置与隔离

```toml
[app]
id = "research-helper"
data_dir = "./.app-data"
plugins = ["chat", "memory", "knowledge", "skills", "tools", "mybusiness"]
system_prompt = "You are the research assistant for this application."

[model]
provider = "openai-compatible"
name = "your-model"
base_url = "https://your-provider.example/v1"
api_key_env = "RESEARCH_APP_MODEL_KEY"

[plugins.chat]
max_rounds = 6
timeout = 180

[plugins.tools]
allow = ["lookup_record"]

[plugins.skills]
directory = "./skills"
selected = ["research"]

[extensions]
mybusiness = "your_installed_package.plugin:plugin"
```

相对路径始终以 manifest 所在目录解析，切换工作目录不会改变数据位置。不同应用必须使用不同数据目录；归属文件记录 `app_id` 和存储版本，阻止其他 app_id 接管、不接管已有非空目录、不允许嵌套应用目录。单目录只允许一个运行时持有进程锁，避免重启恢复影响另一个活跃实例。

```text
.app-data/
  .educlaw-app.json       应用归属与存储版本
  .runtime.lock          进程生命周期锁
  agent/state.sqlite3    会话、请求、运行、事件
  plugins/<plugin>/      插件自己的持久数据
  business/              应用业务数据库和文件
```

模型密钥通过应用指定的环境变量提供，不自动加载任何 `.env`、平台配置或聊天记录。HTTP token 每次启动重新生成；不要把它或模型密钥写入前端构建产物。

这是单用户应用间的默认存储隔离，不是同进程恶意代码沙箱或多租户身份隔离。Python 插件有宿主进程权限；不可信插件需放到独立进程/容器并设计受限 RPC。SDK 不提供多用户鉴权、远程发布或权限审批平台。

## Python SDK

```python
import asyncio
from educlaw import Application

async def main():
    with Application.load("app.toml") as app:
        session = await app.invoke("chat.create_session")
        result = await app.chat(session["session"], "请帮我分析需求", request_id="request_20261022_001")
        print(result["answer"])
        events = await app.invoke("chat.events", {"run_id": result["run_id"]})
        print(events)
        app.set_enabled("memory", False)

asyncio.run(main())
```

插件依赖在启动前排序校验；缺少依赖或存在环直接失败，不擅自打开用户关闭的功能。正在运行操作时禁止切换插件或关闭应用。停用依赖项前须先停用依赖它的插件；停用不删除历史数据，再启用可继续读取。`set_enabled()` 只改变当前实例；重启选项以 manifest 为准。插件启用失败会撤销已注册能力；插件自身在 setup 中创建的外部资源应在异常时自行清理。正常 setup 可返回同步清理函数，按相反顺序执行。

应用可传 `Application(config, model=your_model, plugins=[your_plugin])`；模型实现 `async complete(messages, tools) -> dict`，返回 OpenAI 风格 assistant message，支持 `content` 和 `tool_calls`。无需让应用自定义模型继承某个框架。

## 编写插件

```python
from educlaw import Plugin, Tool

def setup(ctx):
    # ctx.data_dir：当前应用当前插件的目录
    # ctx.application.business_dir：应用自有业务目录
    # ctx.config：manifest 的 [plugins.mybusiness] 参数
    def lookup(record_id):
        return {"id": record_id, "status": "ready"}

    ctx.operation("lookup", lookup, description="查询业务记录")
    ctx.tool(Tool(
        "lookup_record", "Read an application record", lookup,
        {"type": "object", "properties": {"record_id": {"type": "string", "maxLength": 80}},
         "required": ["record_id"], "additionalProperties": False},
    ))
    return lambda: None  # 关闭连接等清理动作

plugin = Plugin("mybusiness", setup, api_version=1)
```

`mybusiness.lookup` 是应用 API，不自动成为模型工具；只有 `ctx.tool()` 注册且 `tools.allow` 列出的工具才能进入模型循环。默认无工具权限，也没有隐含的终端/文件/联网工具。业务 API 面向持有应用访问凭据的客户端，写操作权限需由应用作者设计。

`ctx.context(provider)` 可注册 `provider(session, query)`，返回 JSON 可序列化的参考数据；此内容标为不可信参考，不授予工具权限。每插件最多 12,000 字符，整个消息上下文最多 64,000 字符。工具输入在整批执行前验证；每批最多 8 个调用，每个工具输出最多 16,000 字符。超限直接失败，不悄悄截断成有效结果。大型输出应由插件保存为应用 artifact，并返回引用。

工具 schema 支持显式 `type`（object/array/string/integer/number/boolean/null）、properties、required、additionalProperties 布尔值、items、enum、minimum/maximum、minLength/maxLength、minItems/maxItems，和说明元数据；不支持的 schema 关键字会拒绝注册，不会静默跳过验证。插件 handler 可以同步或异步；同步 handler 应短小无阻塞，长操作使用 async，宿主无法强制终止任意 Python 代码。

插件必须显式通过 SDK 对象传入或在 `[extensions]` 声明已安装模块。关闭的扩展不会导入。没有扫描下载目录并自动执行代码，也没有远程自动安装插件。

插件的可变状态应放在 `setup()` 的实例闭包、`ctx.data_dir` 或应用业务存储中，不要放在模块级全局变量里。Python 的模块导入缓存可跨应用共享代码，第三方插件若自行使用全局变量或硬编码外部路径，仍可能破坏自己的隔离约定。

## HTTP 与界面接入

```powershell
python -m educlaw serve app.toml --port 8765 --origin http://localhost:5173
```

所有接口都需要 `Authorization: Bearer <本次启动 token>`。`GET /v1/app` 返回应用标识、插件开关、可用操作和允许的工具规格；`GET /health` 返回存活状态。实际功能统一为 `POST /v1/operations/<operation>`，JSON 参数对象，成功返回 `{"result": ...}`。

| operation | 参数 | 结果 |
| --- | --- | --- |
| chat.create_session | `{}` | `{session}` |
| chat.sessions | `{}` | 当前应用会话列表 |
| chat.send | `{session,message,request_id?}` | request_id、run_id、answer、status、reused |
| chat.history | `{session}` | 当前会话历史运行 |
| chat.events | `{run_id}` | 有序事件、输入/输出、状态 |
| knowledge.add | `{session,name,text}` | 文档 id；自动挂载到该会话 |
| knowledge.mount | `{session,document,enabled}` | 挂载状态 |
| knowledge.search | `{session,query}` | 相关片段与分数 |
| knowledge.list | `{session}` | 已挂载文档列表 |
| skills.list | `{}` | 应用 Skill 目录 |
| skills.read | `{skill_id}` | 正文 |
| tools.list | `{}` | 当前允许的模型工具 |

事件包括 `run.started`、`model.started/completed`、`tool.started/completed`、`run.completed/failed/interrupted`，可供应用自行画流程图。当前 HTTP 请求等待该轮完成；事件接口可查询已保存记录，尚未提供 token 级 SSE 流式传输或后台任务调度。

关闭的接口返回 403；无此会话/运行返回 404；非法参数 400；运行冲突 409；提供方等执行故障 502。错误响应不回显提供方的原始异常，以免泄露密钥。CORS 默认关闭，仅按明确指定来源放行。适配器固定绑定本机，不应作为互联网多用户服务直接发布；需要远程应用时，可自行实现带身份、授权、限流和 TLS 的部署适配器。

同一 `request_id` 与相同消息重复请求只返回已有成功结果，不重复模型或工具调用。相同 ID 变更内容会拒绝。失败、超时、中断或重启后未完成的请求不会自动重放；应检查事件，再决定是否用新 ID 发起新运行。`tool.started` 后缺少 `tool.completed` 表示实际副作用可能未知，不能据此推断操作没有发生。

## 验证与迁移路线

```powershell
python -m pytest test/test_app_runtime.py -q
```

测试覆盖两个应用使用相同会话 ID 时的历史、资料、事件隔离；插件开关；自定义工具与白名单；整个工具批次预验证；取消与重启；请求幂等；生命周期回滚；HTTP 鉴权、CORS 及真实本机模型协议请求。打包验收另外在不含平台依赖的独立 venv 安装 wheel、启动多个应用、从 HTTP 调用示例业务与 agent API。

接下来迁移旧能力时遵循同一验收标准：先显式注入应用上下文，再移除模块级全局状态，最后以两个应用并行测试证明隔离。工作台最终可以成为使用同一 SDK 的默认应用；这一步不能用直接更换平台数据目录代替。


## 本次验证记录（2026-10-22）

正式 Python 回归 588 项通过，其中新增 SDK 测试 25 项；两个已有手动异步记忆脚本按项目原约定排除。独立 venv 中安装 wheel 后，两个应用进程经真实本机 HTTP 与确定性模型协议夹具完成并行工具调用、业务数据与会话隔离、事件记录、重启及请求幂等验证。安装包只包含 `educlaw` 命名空间和分发元数据，无平台数据库、密钥或缓存。

这项验收证明后端协议、工具链和隔离行为；模型夹具不等于真实 LLM。现有真实模型提供方检查返回 HTTP 402，真实模型验收未通过，需解决提供方计费或访问问题后重试。完整开发记录见[源码中的阶段记录](https://github.com/weiyu687/EduClaw/blob/codex/roadmap-development/docs/DEVELOPMENT_STATUS.md)。
