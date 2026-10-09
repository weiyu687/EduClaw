"""
项目入口

Author: Gongmin Wei
Date: 2026-04-01
"""
import asyncio
from rich.console import Console
import logging
import re
import secrets
from pathlib import Path
from core.security.read_grants import grant, canonical, list_grants, revoke, session_context
from core.security.agent_code_flow import wants_python, draft as draft_agent_code, context as agent_code_context, update as update_agent_code, explain as explain_agent_code
from core.security.code_approval import propose as propose_code, get as get_code, claim as claim_code, reject as reject_code, approved_call

from core.logging import get_logger
from core.usr.startup_info import print_startup_info
from core.agent import EduClawAgent
from core.tasks import TaskManager
from core.tasks.planning import PlanManager
from core.tasks.execution import StepExecutor
from core.tasks.agent_executor import AgentStepExecutor
from core.skills import SkillRegistry

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = get_logger("USER")
console = Console()


async def run_interactive_app():
    print_startup_info()

    # Create Agent -> Init MCP Client -> Start MCP Server
    agent = EduClawAgent()
    task_manager = TaskManager()
    plan_manager = PlanManager(task_manager)
    executor = StepExecutor(task_manager)
    agent_executor = AgentStepExecutor(task_manager)

    pending_read = None

    try:
        logger.info("Main: 正在运行程序 EduClaw...")
        await agent.start()
        console.print(f"[cyan]当前会话: {agent.session_id}[/cyan]")
        console.print("Phase 5.4b: 自然语言明确要求 Python 执行时自动生成待审批代码；/code-approve <token> 后继续回答")
        console.print("Phase 5.4: /code-propose <Python代码> | /code-approve <token> | /code-deny <token> | /code-status <token>")
        console.print("Phase 5.3c: /permissions | /permit <token> <once|session|always> | /deny-read | /allow-read <路径> | /revoke-read <id>")
        console.print("Phase 5.3b: /skills | /agent-step-run <task_id> <序号> <skill_id或-> <tool1,tool2> | /agent-step-approve <task_id> <序号> <token> | /agent-step-result <task_id> <序号>")
        console.print("Phase 5.3: /step-run <task_id> <序号> | /step-approve <task_id> <序号> <token> | /step-result <task_id> <序号>")
        console.print("Phase 5.2: /plan-new <目标> | /plans | /plan <草稿id> | /plan-approve <草稿id> | /plan-reject <草稿id>")
        console.print("Phase 5: /task-new <目标> | /tasks | /task <id> | /step <id> <序号> <状态> | /task-events <id> | /task-cancel <id>")
        console.print("命令: /new | /use <session_id> | /sessions | /runs | /events <run_id> | /status <run_id> | /interrupted | /resume <run_id> | /approve-resume <token>")

        console.print("\n[bold green]EduClaw 已就绪，请输入您的指令 (输入 'exit' 退出):[/bold green]")

        while True:
            user_input = await asyncio.to_thread(input, "You: ")

            if user_input.lower() in ["exit", "quit", "退出"]:
                logger.info("Main: 用户请求关闭程序")
                break

            if not user_input.strip():
                continue

            command = user_input.strip()
            if command.startswith('/code-propose '):
                try:
                    code = user_input.strip()[len('/code-propose '):]
                    request = propose_code(agent.session_id, code)
                    console.print(f"[yellow]高风险工具审批申请\n工具: run_python_code\n代码:\n{request['code']}\nSHA-256: {request['sha256']}\n批准: /code-approve {request['id']}\n拒绝: /code-deny {request['id']}[/yellow]")
                except ValueError as exc:
                    console.print(f'[yellow]申请失败: {exc}[/yellow]')
                continue
            if command.startswith('/code-status '):
                try:
                    request = get_code(agent.session_id, command.split(maxsplit=1)[1])
                    console.print(f"status={request['status']} tool={request['tool']} sha256={request['sha256']}\ncode:\n{request['arguments']['code']}")
                except LookupError as exc:
                    console.print(f'[yellow]{exc}[/yellow]')
                continue
            if command.startswith('/code-deny '):
                rid = command.split(maxsplit=1)[1]
                denied = reject_code(agent.session_id,rid)
                if denied and agent_code_context(agent.session_id, rid):
                    update_agent_code(agent.session_id, rid, 'rejected')
                console.print('已拒绝' if denied else '无法拒绝（已使用或不存在）')
                continue
            if command.startswith('/code-approve '):
                rid = command.split(maxsplit=1)[1]
                try:
                    request = get_code(agent.session_id,rid)
                    console.print(f"[bold yellow]请核对即将执行的代码（Docker 沙箱，无网络）：\n{request['arguments']['code']}\nSHA-256: {request['sha256']}[/bold yellow]")
                    confirmation = (await asyncio.to_thread(input, '输入 EXECUTE 确认本次执行: ')).strip()
                    if confirmation != 'EXECUTE':
                        console.print('已取消，审批请求仍为 pending（可用 /code-deny 拒绝）')
                        continue
                    agent_pending = agent_code_context(agent.session_id, rid)
                    tool, args, digest = claim_code(agent.session_id,rid)
                    if agent_pending:
                        update_agent_code(agent.session_id, rid, 'running')
                    # Approval is consumed BEFORE MCP transport, including timeouts.
                    with session_context(agent.session_id), approved_call(agent.session_id,rid,digest):
                        result = await agent.mcp_client.use_tool(tool,args)
                    console.print(f'[green]执行返回（原始 MCP 结果）:[/green] {result}')
                    if agent_pending:
                        if getattr(result, 'isError', False):
                            update_agent_code(agent.session_id, rid, 'uncertain', str(result))
                            console.print('[yellow]MCP 报告执行错误，禁止自动重试。[/yellow]')
                        else:
                            # The tool has already run; never run it again when explanation fails.
                            update_agent_code(agent.session_id, rid, 'completed', str(result))
                            try:
                                answer = await explain_agent_code(agent.model, agent_pending['request'], args['code'], str(result))
                                console.print(f'\n[bold white]Agent:[/bold white] {answer}\n')
                            except Exception as exc:
                                console.print(f'[yellow]代码已执行，但生成解释失败：{exc}。请勿重复批准执行。[/yellow]')
                except Exception as exc:
                    # A claimed approval is already consumed. Mark interrupted transport
                    # uncertain rather than retrying an operation with side effects.
                    if 'agent_pending' in locals() and agent_pending:
                        try:
                            if agent_code_context(agent.session_id, rid)['status'] == 'running':
                                update_agent_code(agent.session_id, rid, 'uncertain', str(exc))
                        except Exception:
                            pass
                    console.print(f'[yellow]执行失败或已拒绝，禁止自动重试: {exc}[/yellow]')
                finally:
                    agent_pending = None
                continue
            if command == '/permissions':
                for item in list_grants(agent.session_id):
                    console.print(f"{item['id']}  {item['scope']}  {item['path']}  remaining={item['remaining']}")
                continue
            if command.startswith('/revoke-read '):
                try:
                    rid = int(command.split(maxsplit=1)[1])
                    console.print('已撤销' if revoke(rid, agent.session_id) else '未找到授权')
                except ValueError:
                    console.print('[yellow]用法: /revoke-read <授权ID>[/yellow]')
                continue
            if command == '/deny-read':
                pending_read = None
                console.print('已取消待处理的读取授权请求')
                continue
            if command.startswith('/allow-read '):
                path = command.split(maxsplit=1)[1].strip().strip('"')
                try:
                    path = canonical(path)
                    confirm = (await asyncio.to_thread(input, f'确认将此路径授权给当前会话? {path} [输入 YES 确认]: ')).strip()
                    if confirm.upper() == 'YES':
                        grant(path, 'session', agent.session_id)
                        console.print('[green]当前会话读取权限已授予[/green]')
                    else:
                        console.print('已取消')
                except (ValueError, OSError) as exc:
                    console.print(f'[yellow]授权失败: {exc}[/yellow]')
                continue
            if command.startswith('/permit '):
                parts = command.split()
                if len(parts) != 3 or parts[2] not in ('once','session','always') or not pending_read or parts[1] != pending_read['token'] or pending_read['session'] != agent.session_id:
                    console.print('[yellow]授权令牌无效或范围不合法。用法: /permit <token> once|session|always[/yellow]')
                    continue
                request = pending_read
                pending_read = None
                try:
                    grant(request['path'], parts[2], agent.session_id)
                    console.print(f"[green]已授权 {parts[2]}：{request['path']}；正在继续原请求[/green]")
                    with session_context(agent.session_id):
                        response = await agent.chat(request['message'])
                    console.print(f"\n[bold white]Agent:[/bold white] {response}\n")
                except (ValueError, OSError) as exc:
                    console.print(f'[yellow]授权或执行失败: {exc}[/yellow]')
                continue
            if command == '/skills':
                for skill in SkillRegistry().list():
                    console.print(f"{skill['id']}  {skill['name']}  {skill['description']}")
                continue
            if command.startswith('/agent-step-run '):
                try:
                    parts = command.split()
                    if len(parts) != 5:
                        raise ValueError('用法: /agent-step-run <task_id> <序号> <skill_id或-> <tool1,tool2>')
                    tid, pos, skill_id, tools_csv = parts[1], int(parts[2]), parts[3], parts[4]
                    request = agent_executor.request(agent.session_id, tid, pos, skill_id,
                                                     [x.strip() for x in tools_csv.split(',') if x.strip()])
                    console.print(f"[yellow]待审批 Skill={skill_id} Tools={request['tools']}\n"
                                  f"执行: /agent-step-approve {tid} {pos} {request['token']}[/yellow]")
                except (ValueError, LookupError, PermissionError) as exc:
                    console.print(f'[yellow]工具任务申请失败: {exc}[/yellow]')
                continue
            if command.startswith('/agent-step-approve '):
                try:
                    parts = command.split()
                    if len(parts) != 4:
                        raise ValueError('用法: /agent-step-approve <task_id> <序号> <token>')
                    tid, pos, token = parts[1], int(parts[2]), parts[3]
                    agent_executor.approve(agent.session_id, tid, pos, token)
                    result = await agent_executor.execute(agent.session_id, tid, pos, agent)
                    console.print(f"工具步骤结果: {result['status']}\n{result['result']}")
                except Exception as exc:
                    console.print(f'[yellow]工具步骤失败（如执行中断请人工审查，禁止自动重试）: {exc}[/yellow]')
                continue
            if command.startswith('/agent-step-result '):
                try:
                    parts = command.split()
                    if len(parts) != 3:
                        raise ValueError('用法: /agent-step-result <task_id> <序号>')
                    console.print(agent_executor.result(agent.session_id, parts[1], int(parts[2])))
                except (ValueError, LookupError) as exc:
                    console.print(f'[yellow]{exc}[/yellow]')
                continue
            if command.startswith('/plan-new '):
                try:
                    console.print('[cyan]正在生成草稿（不会执行任何工具或保存为任务）...[/cyan]')
                    draft = await plan_manager.generate(agent.session_id, command.split(maxsplit=1)[1], agent.model)
                    console.print(f"计划草稿 ID: {draft['id']}\n目标: {draft['goal']}")
                    for i, step in enumerate(draft['steps'], 1):
                        console.print(f"{i}. {'[需要审批] ' if step['requires_approval'] else ''}{step['title']}")
                    console.print(f"[yellow]审核后输入 /plan-approve {draft['id']} 保存，或 /plan-reject {draft['id']} 放弃。[/yellow]")
                except (ValueError, RuntimeError) as exc:
                    console.print(f'[yellow]生成计划失败: {exc}[/yellow]')
                continue
            if command == '/plans':
                for item in plan_manager.list(agent.session_id):
                    console.print(f"{item['id']}  {item['status']}  {item['goal']}")
                continue
            if command.startswith('/plan '):
                try:
                    console.print(plan_manager.get(agent.session_id, command.split(maxsplit=1)[1]))
                except LookupError as exc:
                    console.print(f'[yellow]{exc}[/yellow]')
                continue
            if command.startswith('/plan-approve '):
                try:
                    task = plan_manager.approve(agent.session_id, command.split(maxsplit=1)[1])
                    console.print(f"[green]计划已审核保存为任务: {task['id']}（{task['progress']['total']} 步）[/green]")
                except (LookupError, ValueError) as exc:
                    console.print(f'[yellow]{exc}[/yellow]')
                continue
            if command.startswith('/plan-reject '):
                try:
                    draft = plan_manager.reject(agent.session_id, command.split(maxsplit=1)[1])
                    console.print(f"计划草稿已拒绝: {draft['id']}")
                except (LookupError, ValueError) as exc:
                    console.print(f'[yellow]{exc}[/yellow]')
                continue
            if command.startswith('/step-run '):
                try:
                    parts = command.split()
                    if len(parts) != 3: raise ValueError('用法: /step-run <task_id> <序号>')
                    tid, pos = parts[1], int(parts[2])
                    state = executor.request(agent.session_id, tid, pos)
                    if state['status'] == 'awaiting_approval':
                        console.print(f"[yellow]步骤需要审批。仅允许模型生成文本，不调用 MCP 工具。\n审批命令: /step-approve {tid} {pos} {state['token']}[/yellow]")
                    else:
                        result = await executor.execute(agent.session_id, tid, pos, agent.model)
                        console.print(f"步骤结果: {result['status']}\n{result['result']}")
                except (ValueError, LookupError, PermissionError, RuntimeError) as exc:
                    console.print(f'[yellow]步骤执行失败: {exc}[/yellow]')
                continue
            if command.startswith('/step-approve '):
                try:
                    parts = command.split()
                    if len(parts) != 4: raise ValueError('用法: /step-approve <task_id> <序号> <token>')
                    tid, pos, token = parts[1], int(parts[2]), parts[3]
                    executor.approve(agent.session_id, tid, pos, token)
                    result = await executor.execute(agent.session_id, tid, pos, agent.model)
                    console.print(f"步骤结果: {result['status']}\n{result['result']}")
                except (ValueError, LookupError, PermissionError, RuntimeError) as exc:
                    console.print(f'[yellow]审批/执行失败: {exc}[/yellow]')
                continue
            if command.startswith('/step-result '):
                try:
                    parts = command.split()
                    if len(parts) != 3: raise ValueError('用法: /step-result <task_id> <序号>')
                    console.print(executor.result(agent.session_id,parts[1],int(parts[2])))
                except (ValueError, LookupError) as exc:
                    console.print(f'[yellow]{exc}[/yellow]')
                continue
            if command.startswith('/task-new '):
                goal = command.split(maxsplit=1)[1]
                console.print('[cyan]逐行输入步骤（空行结束），以 ! 开头表示需要审批的步骤：[/cyan]')
                steps = []
                while True:
                    line = (await asyncio.to_thread(input, 'Step: ')).strip()
                    if not line:
                        break
                    steps.append({'title':line.lstrip('!').strip(), 'requires_approval':line.startswith('!')})
                try:
                    task = task_manager.create(agent.session_id, goal, steps)
                    console.print(f"已创建任务: {task['id']} ({task['progress']['total']} 步)")
                except (ValueError, LookupError) as exc:
                    console.print(f'[yellow]{exc}[/yellow]')
                continue
            if command == '/tasks':
                for task in task_manager.list(agent.session_id):
                    console.print(f"{task['id']}  {task['status']}  {task['goal']}")
                continue
            if command.startswith('/task '):
                try:
                    console.print(task_manager.get(agent.session_id,command.split(maxsplit=1)[1]))
                except LookupError as exc:
                    console.print(f'[yellow]{exc}[/yellow]')
                continue
            if command.startswith('/step '):
                try:
                    if len(command.split()) != 4:
                        console.print('[yellow]用法: /step <task_id> <序号> <in_progress|completed|failed|blocked>[/yellow]')
                        continue
                    _,tid,num,status = command.split(maxsplit=3)
                    task = task_manager.set_step(agent.session_id,tid,int(num),status)
                    console.print(f"步骤 {num}: {status}；任务状态: {task['status']}；进度: {task['progress']['done']}/{task['progress']['total']}")
                except (ValueError, LookupError, PermissionError) as exc:
                    console.print(f'[yellow]{exc}[/yellow]')
                continue
            if command.startswith('/task-events '):
                try:
                    for event in task_manager.events(agent.session_id,command.split(maxsplit=1)[1]):
                        console.print(event)
                except LookupError as exc:
                    console.print(f'[yellow]{exc}[/yellow]')
                continue
            if command.startswith('/task-cancel '):
                try:
                    console.print(task_manager.cancel(agent.session_id,command.split(maxsplit=1)[1])['status'])
                except (LookupError, ValueError) as exc:
                    console.print(f'[yellow]{exc}[/yellow]')
                continue
            if command == '/new':
                import uuid
                agent.set_session_context(str(uuid.uuid4()))
                console.print(f"新会话: {agent.session_id}")
                continue
            if command == '/sessions':
                for item in agent.list_sessions():
                    console.print(f"{item['id']}  {item['updated_at']}")
                continue
            if command.startswith('/use '):
                sid = command.split(maxsplit=1)[1]
                agent.set_session_context(sid)
                console.print(f"已切换到: {agent.session_id}")
                continue
            if command == '/runs':
                for item in agent.list_runs():
                    console.print(f"{item['id']}  {item['status']}")
                continue
            if command == '/interrupted':
                for item in agent.state_manager.get_interrupted_runs(agent.session_id):
                    console.print(f"{item['id']}  interrupted (requires review)")
                continue
            if command.startswith('/resume '):
                rid = command.split(maxsplit=1)[1]
                try:
                    review = await agent.review_resume(rid)
                    console.print(review)
                    if review.get('can_resume'):
                        console.print('[yellow]仅在确认后使用 /approve-resume <approval_token> 继续；不会自动重放工具。[/yellow]')
                    else:
                        console.print('[yellow]恢复已阻止：当前检查点不满足安全条件。[/yellow]')
                except (LookupError, ValueError, RuntimeError) as exc:
                    console.print(f'[yellow]{exc}[/yellow]')
                continue
            if command.startswith('/approve-resume '):
                token = command.split(maxsplit=1)[1]
                try:
                    result = await agent.approve_resume(token)
                    console.print(f"[bold white]恢复结果:[/bold white] {result}")
                except (PermissionError, RuntimeError, LookupError, ValueError) as exc:
                    console.print(f'[yellow]恢复未执行：{exc}[/yellow]')
                continue
            if command.startswith('/status '):
                run = agent.state_manager.get_run(command.split(maxsplit=1)[1])
                if run is None or run['session_id'] != agent.session_id:
                    console.print('未找到当前会话中的运行记录')
                else:
                    console.print(run)
                continue
            if command.startswith('/events '):
                for item in agent.list_events(command.split(maxsplit=1)[1]):
                    console.print(item)
                continue
            # Model may draft code, but only trusted CLI can approve execution.
            # Never let ordinary chat call run_python_code for this route.
            if wants_python(user_input):
                try:
                    request = await draft_agent_code(agent.model, agent.session_id, user_input)
                    console.print(f"[yellow]Agent 已生成待审批 Python 代码（尚未执行）：\n{request['code']}\nSHA-256: {request['sha256']}\n批准: /code-approve {request['id']}\n拒绝: /code-deny {request['id']}[/yellow]")
                except Exception as exc:
                    console.print(f'[yellow]自动生成代码申请失败（未执行任何代码）：{exc}[/yellow]')
                continue
            # Preflight explicit local file paths; the model never authorizes itself.
            # The gateway remains mandatory for every actual MCP call.
            candidates = re.findall(r'[A-Za-z]:\\[^\r\n\"<>|?*]+?\.(?:pdf|docx?|pptx|xlsx?|py)(?=\s|$|[，,。；;）)])', user_input, flags=re.I)
            requested_path = None
            for raw in candidates:
                try:
                    from core.security.global_gateway import _roots
                    from core.security.read_grants import allowed
                    resolved = Path(canonical(raw.strip()))
                    if not any(resolved.is_relative_to(root) for root in _roots()) and not allowed(resolved, agent.session_id):
                        requested_path = str(resolved)
                        break
                except (ValueError, OSError, PermissionError):
                    continue
            if requested_path:
                token = secrets.token_urlsafe(16)
                pending_read = {'token':token, 'path':requested_path, 'message':user_input, 'session':agent.session_id}
                console.print(f"[yellow]需要读取授权：{requested_path}\n"
                              f"仅本次: /permit {token} once\n"
                              f"当前会话: /permit {token} session\n"
                              f"持久授权: /permit {token} always\n"
                              f"拒绝: /deny-read[/yellow]")
                continue
            with session_context(agent.session_id):
                response = await agent.chat(user_input)

            console.print(f"\n[bold white]Agent:[/bold white] {response}\n")

    except Exception as e:
        logger.error(f"Main: 程序发生错误--{e}", exc_info=True)
    finally:
        await agent.stop()
        logger.info("Main: 程序已安全退出")


if __name__ == "__main__":
    try:
        asyncio.run(run_interactive_app())
    except KeyboardInterrupt:
        pass