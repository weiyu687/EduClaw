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
from core.security.tool_dispatcher import route as suggest_route, read_preflight, user_paths, explicit_tool_policy, READ_TOOLS
from core.security.agent_code_flow import wants_python, draft as draft_agent_code, context as agent_code_context, update as update_agent_code, explain as explain_agent_code
from core.security.code_approval import propose as propose_code, get as get_code, claim as claim_code, reject as reject_code, approved_call, fingerprint
from core.security.interrupt_flow import InterruptFlow
from core.security.multi_step_graph import MultiStepFlow, ExecutionLedger, draft_plan, READ_ARGS
from core.security.autonomous_agent import AutonomousStore, classify as classify_autonomous, next_action as autonomous_next, inspect_response, MAX_STEPS
from core.security.read_grants import db_path

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
    interrupt_flow = None
    multi_flow = None
    multi_ledger = None
    autonomous_store = AutonomousStore(db_path().with_name("educlaw_autonomous.sqlite3"))

    try:
        logger.info("Main: 正在运行程序 EduClaw...")
        await agent.start()
        # Independent durable LangGraph checkpoint for approval decisions.
        # No tool execution occurs inside the graph.
        try:
            interrupt_flow = InterruptFlow(db_path().with_name('educlaw_interrupts.sqlite3'))
            console.print('[green]Phase 5.6: LangGraph Interrupt 审批流已启用[/green]')
        except ImportError:
            console.print('[yellow]Phase 5.6 未启用：请安装 langgraph-checkpoint-sqlite[/yellow]')
        try:
            multi_flow = MultiStepFlow(db_path().with_name('educlaw_multi_checkpoints.sqlite3'))
            multi_ledger = ExecutionLedger(db_path().with_name('educlaw_multi_claims.sqlite3'))
            console.print('[green]Phase 5.6c 多步骤执行图已启用[/green]')
        except ImportError:
            console.print('[yellow]Phase 5.6c 不可用：请安装 langgraph-checkpoint-sqlite[/yellow]')
        console.print(f"[cyan]当前会话: {agent.session_id}[/cyan]")
        console.print('Phase 5.6c: /multi <任务> | /multi-status <task> | /multi-approve <task> | /multi-deny <task>')
        console.print("Phase 5.6: /flow-code <Python代码> | /flow-status <token> | /flow-approve <token> | /flow-deny <token>")
        console.print("Phase 5.5: /auto on|off | /auto-status；自主建议路由（权限仍由 CLI 与 MCP 网关控制）")
        auto_mode = True
        console.print("Phase 5.4b: 自然语言明确要求 Python 执行时自动生成待审批代码；/code-approve <token> 后继续回答")
        console.print("Phase 5.4: /code-propose <Python代码> | /code-approve <token> | /code-deny <token> | /code-status <token>")
        console.print("Phase 5.3c: /permissions | /permit <token> <once|session|always> | /deny-read | /allow-read <路径> | /revoke-read <id>")
        console.print("Phase 5.3b: /skills | /agent-step-run <task_id> <序号> <skill_id或-> <tool1,tool2> | /agent-step-approve <task_id> <序号> <token> | /agent-step-result <task_id> <序号>")
        console.print("Phase 5.3: /step-run <task_id> <序号> | /step-approve <task_id> <序号> <token> | /step-result <task_id> <序号>")
        console.print("Phase 5.2: /plan-new <目标> | /plans | /plan <草稿id> | /plan-approve <草稿id> | /plan-reject <草稿id>")
        console.print("Phase 5: /task-new <目标> | /tasks | /task <id> | /step <id> <序号> <状态> | /task-events <id> | /task-cancel <id>")
        console.print("自主任务：自然语言输入 | /approve <任务ID> | /deny <任务ID> | /task-status <任务ID> | /task-list | /task-continue <任务ID> | /task-replan <任务ID>")
        console.print("命令: /new | /use <session_id> | /sessions | /runs | /events <run_id> | /status <run_id> | /interrupted | /resume <run_id> | /approve-resume <token>")

        console.print("\n[bold green]EduClaw 已就绪，请输入您的指令 (输入 'exit' 退出):[/bold green]")

        async def autonomous_plan(task_id):
            state = autonomous_store.get(agent.session_id, task_id)
            if state['status'] != 'planning':
                return
            if state['step'] >= MAX_STEPS:
                autonomous_store.decision(agent.session_id, task_id,
                    {'action':'finish','answer':'已达到安全步骤上限，请查看已完成结果并发起新任务。'})
                console.print('[yellow]已达到步骤上限，任务停止。[/yellow]')
                return
            # Retry only LLM planning/JSON errors; no MCP operation is retried.
            decision=None
            for attempt in range(2):
                try:
                    decision = await autonomous_next(agent.model, state['goal'], state['results'], user_paths(state['goal']))
                    break
                except Exception as exc:
                    failure=autonomous_store.planning_error(agent.session_id,task_id,exc)
                    if failure['status']=='needs_attention' or attempt==1:
                        console.print(f"[yellow]规划失败（未执行工具）：{exc}；任务 {task_id}，累计失败 {failure['planning_failures']} 次。"
                                      f"可用 /task-continue {task_id} 继续安全规划；达到上限后用 /task-replan。[/yellow]")
                        return
                    console.print('[dim]规划输出无效，正在安全地重新生成计划（不会重试工具）[/dim]')
            if decision['action'] == 'finish':
                autonomous_store.decision(agent.session_id, task_id, decision)
                console.print(f"\n[bold white]Agent:[/bold white] {decision['answer']}\n")
                return
            # Every step gets a real LangGraph interrupt, even after prior tool results.
            if multi_flow is None:
                raise RuntimeError('LangGraph checkpoint unavailable; refusing to execute')
            flow_id, _ = multi_flow.begin(agent.session_id, state['goal'], [decision['step']])
            autonomous_store.decision(agent.session_id, task_id,
                {'action':'tool','step':{**decision['step'],'_flow_id':flow_id}})
            console.print(f"[yellow]任务 {task_id} 第 {state['step']+1} 步等待审批："
                          f"{decision['step']['tool']} {decision['step']['arguments']}\n"
                          f"批准: /approve {task_id} | 拒绝: /deny {task_id}[/yellow]")

        async def autonomous_approve(task_id):
            state=autonomous_store.get(agent.session_id,task_id)
            if state['status'] != 'pending' or not state['pending']:
                raise PermissionError('任务没有待审批步骤')
            step=state['pending']
            flow_id=step['_flow_id']
            checkpoint=multi_flow.pending(agent.session_id,flow_id)
            if checkpoint['step'] != {'tool':step['tool'],'arguments':step['arguments']}:
                raise PermissionError('Checkpoint/approval parameters mismatch')
            console.print(f"[bold yellow]第 {state['step']+1} 步审批\n工具: {step['tool']}\n参数: {step['arguments']}[/bold yellow]")
            confirm=(await asyncio.to_thread(input,'输入 EXECUTE 确认本次操作: ')).strip()
            if confirm != 'EXECUTE':
                console.print('未执行，仍等待审批')
                return
            # Durable claim first. A crash leaves claimed state; never auto-replay.
            autonomous_store.claim(agent.session_id,task_id)
            outcome={'status':'uncertain','output':'Execution claimed; outcome unknown'}
            try:
                tool,args=step['tool'],step['arguments']
                if tool=='run_python_code':
                    req=propose_code(agent.session_id,args['code'])
                    _,exact,digest=claim_code(agent.session_id,req['id'])
                    if exact!=args: raise PermissionError('Code changed')
                    with session_context(agent.session_id),approved_call(agent.session_id,req['id'],digest):
                        response=await agent.mcp_client.use_tool(tool,exact)
                elif tool in READ_ARGS:
                    grant(args[READ_ARGS[tool]],'once',agent.session_id)
                    with session_context(agent.session_id):
                        response=await agent.mcp_client.use_tool(tool,args)
                else:raise PermissionError('Unsupported tool')
                checked=inspect_response(tool,response)
                outcome={'status':checked['status'],'output':checked['output']}
                summary=checked['summary']
            except Exception as exc:
                outcome={'status':'uncertain','output':str(exc)}
                summary='工具调用结果不确定，已停止自动执行'
            autonomous_store.record(agent.session_id,task_id,outcome)
            console.print(f"[cyan]{summary}；步骤状态: {outcome['status']}[/cyan]")
            if outcome['status']!='completed':
                console.print(f"[yellow]诊断: {outcome['output'][:500]}[/yellow]")
            try:
                multi_flow.resume(agent.session_id,flow_id,
                    {**outcome,'status':'uncertain' if outcome['status']=='failed' else outcome['status']})
            except Exception as exc:
                console.print(f'[yellow]检查点恢复异常，禁止重新执行此步骤: {exc}[/yellow]')
                return
            if outcome['status']=='completed':
                try:
                    await autonomous_plan(task_id)
                except Exception as exc:
                    console.print(f'[yellow]后续规划失败；工具不会重试。任务 {task_id} 可查询: {exc}[/yellow]')
            else:
                console.print('[yellow]步骤失败或结果不确定，任务停止；禁止自动重试。[/yellow]')

        while True:
            user_input = await asyncio.to_thread(input, "You: ")

            if user_input.lower() in ["exit", "quit", "退出"]:
                logger.info("Main: 用户请求关闭程序")
                break

            if not user_input.strip():
                continue

            command = user_input.strip()
            # Recovery commands must never fall through to natural-language planning.
            if command == '/task-continue':
                recoverable = [item for item in autonomous_store.recoverable(agent.session_id)
                               if item['status'] in ('pending', 'planning')]
                if len(recoverable) == 1:
                    command = '/task-continue ' + recoverable[0]['id']
                    console.print(f"[dim]继续当前会话任务: {recoverable[0]['id']}[/dim]")
                elif not recoverable:
                    console.print('[yellow]当前会话没有可继续的任务；请使用 /task-list 查看任务状态。[/yellow]')
                    continue
                else:
                    console.print('[yellow]存在多个可继续任务，请使用 /task-continue <任务ID> 指定：[/yellow]')
                    for item in recoverable:
                        console.print(f"  {item['id']} | {item['status']}")
                    continue
            if command in ('/task-replan', '/task-status', '/approve', '/deny'):
                console.print(f'[yellow]缺少任务ID。用法: {command} <任务ID>[/yellow]')
                continue
            if command.startswith('/') and command.split()[0] in (
                    '/task-continue', '/task-replan', '/task-status', '/approve', '/deny') \
                    and len(command.split()) != 2:
                console.print('[yellow]命令格式错误：请提供一个任务ID。[/yellow]')
                continue
            if command == '/task-list':
                tasks=autonomous_store.recoverable(agent.session_id)
                if not tasks: console.print('[dim]当前会话没有待处理任务[/dim]')
                for item in tasks:
                    console.print(f"{item['id']} | {item['status']} | 已处理 {item['step']} 步 | {item['last_error'][:100]}")
                continue
            if command.startswith('/task-continue ') or command.startswith('/task-replan '):
                task_id=command.split(maxsplit=1)[1]
                try:
                    state=autonomous_store.get(agent.session_id,task_id)
                    if state['status']=='needs_attention' and command.startswith('/task-replan '):
                        state=autonomous_store.reopen_planning(agent.session_id,task_id)
                    if state['status']=='planning':
                        await autonomous_plan(task_id)
                    elif state['status']=='pending':
                        step=state['pending']
                        if multi_flow is None: raise RuntimeError('LangGraph checkpoint unavailable')
                        checkpoint=multi_flow.pending(agent.session_id,step['_flow_id'])
                        if checkpoint['step'] != {'tool':step['tool'],'arguments':step['arguments']}:
                            raise PermissionError('Checkpoint/approval parameters mismatch')
                        console.print(f"[yellow]等待审批：{step['tool']} {step['arguments']}\n"
                                      f"批准: /approve {task_id} | 拒绝: /deny {task_id}[/yellow]")
                    elif state['status'] in ('claimed','uncertain','failed'):
                        console.print('[yellow]此任务存在已认领或结果不确定的操作，禁止自动重放；请人工核查执行结果。[/yellow]')
                    else:
                        console.print(f"[yellow]任务状态 {state['status']} 不可继续；规划错误可用 /task-replan {task_id}[/yellow]")
                except Exception as exc:
                    console.print(f'[yellow]恢复失败，未执行工具: {exc}[/yellow]')
                continue
            if command.startswith('/task-status '):
                try:
                    state=autonomous_store.get(agent.session_id,command.split(maxsplit=1)[1])
                    console.print({k:v for k,v in state.items() if k != 'goal'})
                except Exception as exc: console.print(f'[yellow]查询失败: {exc}[/yellow]')
                continue
            if command.startswith('/approve '):
                try: await autonomous_approve(command.split(maxsplit=1)[1])
                except Exception as exc: console.print(f'[yellow]审批失败，未重试工具: {exc}[/yellow]')
                continue
            if command.startswith('/deny '):
                try:
                    task_id=command.split(maxsplit=1)[1]
                    state=autonomous_store.get(agent.session_id,task_id)
                    flow_id=state['pending']['_flow_id']
                    multi_flow.resume(agent.session_id,flow_id,{'status':'denied','output':'User denied'})
                    autonomous_store.deny(agent.session_id,task_id)
                    console.print('[yellow]已拒绝，任务停止[/yellow]')
                except Exception as exc: console.print(f'[yellow]拒绝失败: {exc}[/yellow]')
                continue
            # Phase 5.6c: multi-step graph. Only the CLI executes side effects.
            if command.startswith('/multi '):
                if multi_flow is None:
                    console.print('[yellow]多步骤图不可用，请安装 checkpoint-sqlite[/yellow]')
                    continue
                try:
                    goal = command[len('/multi '):].strip()
                    policy = explicit_tool_policy(goal)
                    if policy and policy[1] == 'deny':
                        raise PermissionError(f'禁止的指定工具: {policy[0]}')
                    steps = await draft_plan(agent.model, goal)
                    task, pending = multi_flow.begin(agent.session_id, goal, steps)
                    console.print(f'[cyan]多步骤任务 {task}：共 {len(steps)} 步[/cyan]')
                    for n, step in enumerate(steps, 1):
                        console.print(f"  {n}. {step['tool']} {step['arguments']}")
                    console.print(f"[yellow]等待第 1 步审批: /multi-approve {task} 或 /multi-deny {task}[/yellow]")
                except Exception as exc:
                    console.print(f'[yellow]多步骤任务创建失败，未执行工具: {exc}[/yellow]')
                continue
            if command.startswith('/multi-status '):
                try:
                    task = command.split(maxsplit=1)[1]
                    snap = multi_flow.snapshot(agent.session_id, task)
                    console.print(f"status={snap.values['status']} index={snap.values['index']}/{len(snap.values['steps'])} results={snap.values['results']}")
                    if 'gate' in snap.next:
                        console.print(f"待审批: {snap.values['steps'][snap.values['index']]}")
                    if multi_ledger and snap.values['index'] < len(snap.values['steps']):
                        claimed = multi_ledger.status(agent.session_id, task, snap.values['index'])
                        if claimed: console.print(f'[yellow]当前步骤执行记录: {claimed}，不可再次执行[/yellow]')
                except Exception as exc:
                    console.print(f'[yellow]查询失败: {exc}[/yellow]')
                continue
            if command.startswith('/multi-deny '):
                try:
                    task = command.split(maxsplit=1)[1]
                    pending = multi_flow.pending(agent.session_id, task)
                    if multi_ledger.status(agent.session_id, task, pending['index']):
                        raise PermissionError('步骤已经提交执行，不能改为拒绝')
                    multi_ledger.claim(agent.session_id, task, pending['index'])
                    multi_ledger.finish(agent.session_id, task, pending['index'], 'denied')
                    result = multi_flow.resume(agent.session_id, task, {'status':'denied'})
                    console.print(f"[yellow]已拒绝，任务结束: {result['state']['status']}[/yellow]")
                except Exception as exc:
                    console.print(f'[yellow]拒绝失败: {exc}[/yellow]')
                continue
            if command.startswith('/multi-approve '):
                try:
                    task = command.split(maxsplit=1)[1]
                    pending = multi_flow.pending(agent.session_id, task)
                    idx, step = pending['index'], pending['step']
                    if multi_ledger.status(agent.session_id, task, idx):
                        raise PermissionError('步骤已被认领，可能已经执行；禁止重复执行')
                    console.print(f"[bold yellow]多步骤审批：任务 {task} 第 {idx+1} 步\n工具: {step['tool']}\n参数: {step['arguments']}[/bold yellow]")
                    confirmation = (await asyncio.to_thread(input, '输入 EXECUTE 确认当前步骤: ')).strip()
                    if confirmation != 'EXECUTE':
                        console.print('未执行，仍等待审批')
                        continue
                    # Durable claim BEFORE any tool call. Crash => uncertain, never replay.
                    multi_ledger.claim(agent.session_id, task, idx)
                    outcome = {'status':'uncertain','output':'Execution claimed; outcome unknown'}
                    try:
                        tool, args = step['tool'], step['arguments']
                        if tool == 'run_python_code':
                            req = propose_code(agent.session_id, args['code'])
                            _, exact_args, digest = claim_code(agent.session_id, req['id'])
                            if exact_args != args: raise PermissionError('Code arguments changed')
                            with session_context(agent.session_id), approved_call(agent.session_id, req['id'], digest):
                                response = await agent.mcp_client.use_tool(tool, exact_args)
                        elif tool in READ_ARGS:
                            grant(args[READ_ARGS[tool]], 'once', agent.session_id)
                            with session_context(agent.session_id):
                                response = await agent.mcp_client.use_tool(tool, args)
                        else:
                            raise PermissionError('Unsupported tool')
                        outcome = {'status':'uncertain' if getattr(response,'isError',False) else 'completed',
                                   'output':str(response)[:20000]}
                    except Exception as exc:
                        outcome = {'status':'uncertain','output':str(exc)}
                    multi_ledger.finish(agent.session_id, task, idx, outcome['status'])
                    console.print(f"[cyan]步骤结果: {outcome['status']}\n{outcome['output']}[/cyan]")
                    try:
                        next_step = multi_flow.resume(agent.session_id, task, outcome)
                        if next_step.get('finished'):
                            state = next_step['state']
                            console.print(f"[green]任务结束：{state['status']}；已处理 {len(state['results'])} 步[/green]")
                            if state['status'] == 'completed':
                                try:
                                    from langchain_core.messages import SystemMessage, HumanMessage
                                    from core.security.agent_code_flow import _content
                                    report = await agent.model.ainvoke([
                                        SystemMessage(content='根据给定任务和工具结果总结。只可依据结果，不调用工具，不得虚构。'),
                                        HumanMessage(content=str({'goal':state['goal'],'results':state['results']})[:22000])])
                                    console.print(f"\n[bold white]Agent:[/bold white] {_content(report)}")
                                except Exception as exc:
                                    console.print(f'[yellow]结果总结失败（不会重新执行工具）: {exc}[/yellow]')
                        else:
                            console.print(f"[yellow]第 {next_step['index']+1} 步等待审批: {next_step['step']}\n/multi-approve {task} 或 /multi-deny {task}[/yellow]")
                    except Exception as exc:
                        console.print(f'[yellow]执行已认领，但恢复检查点失败；禁止重试: {exc}[/yellow]')
                except Exception as exc:
                    console.print(f'[yellow]多步骤审批失败（未执行新工具）: {exc}[/yellow]')
                continue
            if command == '/auto-status':
                console.print(f"自动路由: {'on' if auto_mode else 'off'}")
                continue
            if command in ('/auto on', '/auto off'):
                auto_mode = command.endswith('on')
                console.print(f"自动路由已{'启用' if auto_mode else '关闭'}")
                continue
            if command.startswith('/flow-code '):
                if interrupt_flow is None:
                    console.print('[yellow]请先安装 langgraph-checkpoint-sqlite 并重启。[/yellow]')
                    continue
                try:
                    req = propose_code(agent.session_id, command[len('/flow-code '):])
                    full = get_code(agent.session_id, req['id'])
                    interrupt_flow.begin(agent.session_id, full)
                    console.print(f"[yellow]LangGraph 已中断等待审批\n工具: run_python_code\n代码:\n{req['code']}\nSHA-256: {req['sha256']}\n批准: /flow-approve {req['id']}\n拒绝: /flow-deny {req['id']}[/yellow]")
                except Exception as exc:
                    console.print(f'[yellow]流程创建失败（未执行代码）: {exc}[/yellow]')
                continue
            if command.startswith('/flow-status '):
                try:
                    rid = command.split(maxsplit=1)[1]
                    req = get_code(agent.session_id, rid)
                    status = 'pending' if interrupt_flow and req['status'] == 'pending' and interrupt_flow.pending(agent.session_id, rid) else req['status']
                    console.print(f"workflow={status}, approval={req['status']}, digest={req['sha256']}")
                except Exception as exc:
                    console.print(f'[yellow]查询失败: {exc}[/yellow]')
                continue
            if command.startswith('/flow-deny '):
                try:
                    rid = command.split(maxsplit=1)[1]
                    interrupt_flow.pending(agent.session_id, rid)
                    if not reject_code(agent.session_id, rid):
                        raise PermissionError('审批已消耗或不存在')
                    interrupt_flow.finish(agent.session_id, rid, {'status':'denied'})
                    if agent_code_context(agent.session_id, rid):
                        update_agent_code(agent.session_id, rid, 'rejected')
                    console.print('[yellow]已拒绝，LangGraph 从断点恢复并结束。[/yellow]')
                except Exception as exc:
                    console.print(f'[yellow]拒绝失败: {exc}[/yellow]')
                continue
            if command.startswith('/flow-approve '):
                try:
                    rid = command.split(maxsplit=1)[1]
                    state = interrupt_flow.pending(agent.session_id, rid)
                    req = get_code(agent.session_id, rid)
                    if req['status'] != 'pending' or req['sha256'] != state['digest'] or req['arguments'] != state['arguments']:
                        raise PermissionError('审批状态或参数不匹配')
                    console.print(f"[bold yellow]LangGraph 暂停点：run_python_code\n代码:\n{req['arguments']['code']}\nSHA-256: {req['sha256']}[/bold yellow]")
                    confirmation = (await asyncio.to_thread(input, '输入 EXECUTE 确认本次执行: ')).strip()
                    if confirmation != 'EXECUTE':
                        console.print('取消执行；仍等待审批')
                        continue
                    tool, args, digest = claim_code(agent.session_id, rid)
                    # Consumed BEFORE transport. Failure is uncertain, never retry.
                    try:
                        with session_context(agent.session_id), approved_call(agent.session_id, rid, digest):
                            result = await agent.mcp_client.use_tool(tool, args)
                        if getattr(result, 'isError', False):
                            outcome = {'status':'uncertain','output':str(result)}
                        else:
                            outcome = {'status':'completed','output':str(result)}
                    except Exception as exc:
                        outcome = {'status':'uncertain','output':str(exc)}
                    try:
                        interrupt_flow.finish(agent.session_id, rid, outcome)
                    except Exception as exc:
                        console.print(f'[yellow]执行已消耗审批，但恢复 checkpoint 失败: {exc}[/yellow]')
                    console.print(f"执行状态: {outcome['status']}\n{outcome['output']}")
                    context = agent_code_context(agent.session_id, rid)
                    if context:
                        update_agent_code(agent.session_id, rid, outcome['status'], outcome['output'])
                        if outcome['status'] == 'completed':
                            try:
                                explanation = await explain_agent_code(agent.model, context['request'], args['code'], outcome['output'])
                                console.print(f"\n[bold white]Agent:[/bold white] {explanation}\n")
                            except Exception as exc:
                                console.print(f'[yellow]结果解释失败（代码不会重新执行）: {exc}[/yellow]')
                except Exception as exc:
                    console.print(f'[yellow]审批失败（未执行）: {exc}[/yellow]')
                continue
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
                if interrupt_flow is not None:
                    try:
                        interrupt_flow.pending(agent.session_id, rid)
                    except (LookupError, PermissionError):
                        pass
                    else:
                        console.print('[yellow]该审批属于 LangGraph 工作流，请使用 /flow-deny[/yellow]')
                        continue
                denied = reject_code(agent.session_id,rid)
                if denied and agent_code_context(agent.session_id, rid):
                    update_agent_code(agent.session_id, rid, 'rejected')
                console.print('已拒绝' if denied else '无法拒绝（已使用或不存在）')
                continue
            if command.startswith('/code-approve '):
                rid = command.split(maxsplit=1)[1]
                try:
                    if interrupt_flow is not None:
                        try:
                            interrupt_flow.pending(agent.session_id, rid)
                        except LookupError:
                            pass
                        except PermissionError:
                            pass
                        else:
                            raise PermissionError('该审批属于 LangGraph 工作流，请使用 /flow-approve')
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
                if pending_read and interrupt_flow and pending_read.get('workflow'):
                    try:
                        interrupt_flow.finish(agent.session_id, pending_read['token'], {'status': 'denied'})
                    except Exception as exc:
                        console.print(f'[yellow]读取拒绝已记录，但检查点恢复失败: {exc}[/yellow]')
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
                    if request.get('workflow'):
                        state = interrupt_flow.pending(agent.session_id, request['token'])
                        if (state['tool'] != request['tool'] or
                                state['arguments'] != request['arguments'] or
                                state['digest'] != fingerprint(request['tool'], request['arguments'])):
                            raise PermissionError('读取审批参数与检查点不匹配')
                    grant(request['path'], parts[2], agent.session_id)
                    console.print(f"[green]已授权 {parts[2]}：{request['path']}；正在继续原请求[/green]")
                    with session_context(agent.session_id):
                        response = await agent.chat(request['message'])
                    console.print(f"\n[bold white]Agent:[/bold white] {response}\n")
                    if request.get('workflow'):
                        interrupt_flow.finish(agent.session_id, request['token'], {'status':'completed', 'output':'Read permission granted and agent request returned'})
                except Exception as exc:
                    if request.get('workflow'):
                        try:
                            interrupt_flow.finish(agent.session_id, request['token'], {'status':'uncertain', 'output':str(exc)})
                        except Exception:
                            pass
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
            # Phase 5.5.1: explicit tool requests are handled before model routing.
            # A denied tool must never be silently converted into run_python_code.
            explicit_policy = explicit_tool_policy(user_input)
            if explicit_policy and explicit_policy[1] == 'deny':
                tool_name, _, explanation = explicit_policy
                console.print(f"[yellow]检测到指定工具：{tool_name}\n"
                              f"安全策略：{explanation}\n"
                              "执行状态：DENIED；未执行任何工具。[/yellow]")
                continue
            # Phase 5.7: ordinary natural language is the primary task interface.
            # Existing developer commands and explicit forbidden-tool policy stay authoritative.
            if auto_mode and multi_flow is not None:
                try:
                    if await classify_autonomous(agent.model,user_input):
                        task_id=autonomous_store.create(agent.session_id,user_input)
                        console.print(f'[cyan]Agent 正在规划任务 {task_id}[/cyan]')
                        await autonomous_plan(task_id)
                        continue
                except Exception as exc:
                    console.print(f'[yellow]自动任务规划失败（未执行新工具）: {exc}[/yellow]')
                    continue
            # Phase 5.5: model suggests a route, never an authorization.
            # Explicit code intent retains Phase 5.4b compatibility even if auto is off.
            selected = None
            if auto_mode and explicit_policy is None:
                try:
                    selected = await suggest_route(agent.model, user_input)
                except Exception as exc:
                    logger.warning(f'Router failed; falling back to conservative routing: {exc}')
            # Explicit Python intent must not fall through to unrestricted chat.
            do_python = (explicit_policy is not None and explicit_policy[1] == 'python') or (explicit_policy is None and (wants_python(user_input) or (auto_mode and selected and selected.action == 'python')))
            if do_python:
                try:
                    request = await draft_agent_code(agent.model, agent.session_id, user_input)
                    if interrupt_flow is not None:
                        interrupt_flow.begin(agent.session_id, get_code(agent.session_id, request['id']))
                        approve_cmd, deny_cmd = '/flow-approve', '/flow-deny'
                    else:
                        approve_cmd, deny_cmd = '/code-approve', '/code-deny'
                    console.print(f"[yellow]Agent 已生成待审批 Python 代码（尚未执行）：\n{request['code']}\nSHA-256: {request['sha256']}\n批准: {approve_cmd} {request['id']}\n拒绝: {deny_cmd} {request['id']}[/yellow]")
                except Exception as exc:
                    console.print(f'[yellow]自动生成代码申请失败（未执行任何代码）：{exc}[/yellow]')
                continue
            # Always preflight explicit user paths, even if model proposes chat.
            # Never approve paths inferred or invented by the model.
            candidates = user_paths(user_input)
            requested_path = None
            path_error = None
            for raw in candidates:
                try:
                    requested_path = read_preflight(raw, agent.session_id)
                    if requested_path:
                        break
                except (ValueError, OSError, PermissionError) as exc:
                    path_error = f'{raw}: {exc}'
                    break
            if path_error:
                console.print(f'[yellow]文件预检查失败（未执行工具）：{path_error}[/yellow]')
                continue
            if requested_path:
                token = secrets.token_urlsafe(16)
                ext = requested_path.rsplit('.', 1)[-1].lower()
                tool = READ_TOOLS.get(ext)
                args = None
                if interrupt_flow is not None and tool:
                    try:
                        state = interrupt_flow.begin_read(agent.session_id, token, tool, requested_path)
                        args = state['arguments']
                    except Exception as exc:
                        console.print(f'[yellow]读取审批工作流创建失败（未授权）: {exc}[/yellow]')
                        continue
                pending_read = {'token':token, 'path':requested_path, 'message':user_input,
                                'session':agent.session_id, 'workflow':bool(args),
                                'tool':tool, 'arguments':args}
                console.print(f"[yellow]需要读取授权：{requested_path}\n"
                              f"仅本次: /permit {token} once\n"
                              f"当前会话: /permit {token} session\n"
                              f"持久授权: /permit {token} always\n"
                              f"拒绝: /deny-read[/yellow]")
                continue
            # Agent chooses its read-only MCP tool using its existing LangGraph setup.
            # All actual calls are still checked by the global gateway.
            with session_context(agent.session_id):
                response = await agent.chat(user_input)

            console.print(f"\n[bold white]Agent:[/bold white] {response}\n")

    except Exception as e:
        logger.error(f"Main: 程序发生错误--{e}", exc_info=True)
    finally:
        if multi_flow is not None:
            multi_flow.close()
        if interrupt_flow is not None:
            interrupt_flow.close()
        await agent.stop()
        logger.info("Main: 程序已安全退出")


if __name__ == "__main__":
    try:
        asyncio.run(run_interactive_app())
    except KeyboardInterrupt:
        pass