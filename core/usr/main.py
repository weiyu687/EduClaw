"""
项目入口

Author: Gongmin Wei
Date: 2026-04-01
"""
import asyncio
from rich.console import Console
import logging

from core.logging import get_logger
from core.usr.startup_info import print_startup_info
from core.agent import EduClawAgent
from core.tasks import TaskManager
from core.tasks.planning import PlanManager

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = get_logger("USER")
console = Console()


async def run_interactive_app():
    print_startup_info()

    # Create Agent -> Init MCP Client -> Start MCP Server
    agent = EduClawAgent()
    task_manager = TaskManager()
    plan_manager = PlanManager(task_manager)

    try:
        logger.info("Main: 正在运行程序 EduClaw...")
        await agent.start()
        console.print(f"[cyan]当前会话: {agent.session_id}[/cyan]")
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