"""Deterministic, isolated Phase-4 checkpoint recovery demo.

Run from project root:
    python -m test.phase4_resume_demo prepare
    python -m test.phase4_resume_demo resume
    python -m test.phase4_resume_demo status

Uses real LangGraph + AsyncSqliteSaver + project's StateManager and SafeCheckpointRecovery.
No MCP, LLM, Docker, external calls or tools. Uses isolated data/phase4_demo/ DBs.
"""
import argparse
import asyncio
import json
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from core.state import StateManager
from core.state.recovery import SafeCheckpointRecovery


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'phase4_demo'
META = DATA / 'state.sqlite3'
CHECKPOINTS = DATA / 'checkpoints.sqlite3'
RECORD = DATA / 'active.json'


class DemoState(TypedDict):
    messages: list


def make_graph(checkpointer):
    def prepare(state: DemoState):
        return {}  # intentionally no tool side effects

    def model(state: DemoState):
        return {'messages': [AIMessage(content='PHASE4_RESUME_SUCCESS')]}

    builder = StateGraph(DemoState)
    builder.add_node('prepare', prepare)
    builder.add_node('model', model)
    builder.add_edge(START, 'prepare')
    builder.add_edge('prepare', 'model')
    builder.add_edge('model', END)
    # Persistent breakpoint: model is pending, no external process needs killing.
    return builder.compile(checkpointer=checkpointer, interrupt_before=['model'])


def get_store():
    DATA.mkdir(parents=True, exist_ok=True)
    return StateManager(str(META))


def load_record():
    if not RECORD.exists():
        raise SystemExit('No demo run. First execute: python -m test.phase4_resume_demo prepare')
    return json.loads(RECORD.read_text(encoding='utf-8'))


async def prepare_demo():
    store = get_store()
    # New session per test run; never overwrite the checkpoint of an earlier demo.
    session_id = store.ensure_session()
    run_id = store.start_run(session_id, 'PHASE4_DEMO_NO_TOOLS')
    try:
        async with AsyncExitStack() as stack:
            saver = await stack.enter_async_context(AsyncSqliteSaver.from_conn_string(str(CHECKPOINTS)))
            await saver.setup()
            graph = make_graph(saver)
            config = {'configurable': {'thread_id': session_id}}
            await graph.ainvoke({'messages': [HumanMessage(content='PHASE4_DEMO')]}, config=config)
            snapshot = await graph.aget_state(config)
            nodes = tuple(snapshot.next or ())
            if nodes != ('model',):
                raise RuntimeError(f'Expected pending model node, got {nodes!r}')
            cp_id = (snapshot.config.get('configurable') or {}).get('checkpoint_id')
            if not cp_id:
                raise RuntimeError('Checkpoint was not persisted')
        # Simulate next startup's abandoned-run scan, without killing any process.
        store.mark_interrupted()
        RECORD.write_text(json.dumps({'session_id': session_id, 'run_id': run_id}, indent=2), encoding='utf-8')
        print('PREPARED: process exited at a persisted, tool-free model checkpoint')
        print('run_id:', run_id)
        print('session_id:', session_id)
        print('checkpoint_id:', cp_id)
        print('next_nodes:', nodes)
        print('Run the resume command in a NEW terminal process.')
    except BaseException:
        store.finish_run(run_id, 'failed', error='Demo prepare failed')
        raise


async def resume_demo(yes: bool):
    record = load_record()
    store = get_store()
    async with AsyncExitStack() as stack:
        saver = await stack.enter_async_context(AsyncSqliteSaver.from_conn_string(str(CHECKPOINTS)))
        await saver.setup()
        graph = make_graph(saver)
        recovery = SafeCheckpointRecovery(store, graph)
        decision = await recovery.review(record['run_id'], record['session_id'])
        print('REVIEW:', json.dumps({k: v for k, v in decision.to_dict().items() if k != 'approval_token'}, ensure_ascii=False, indent=2, default=str))
        if not decision.can_resume:
            raise SystemExit('BLOCKED: review did not authorize recovery')
        if not decision.approval_token:
            raise RuntimeError('No approval token')
        if not yes:
            answer = input('Type APPROVE to resume this tool-free demo checkpoint: ').strip()
            if answer != 'APPROVE':
                print('CANCELLED: no checkpoint execution')
                return
        result = await recovery.approve_and_resume(decision.approval_token, record['session_id'])
        messages = result.get('messages', [])
        actual = getattr(messages[-1], 'content', None) if messages else None
        if actual != 'PHASE4_RESUME_SUCCESS':
            raise RuntimeError(f'Unexpected resume output: {actual!r}')
        print('RESUMED:', actual)
        print('RUN STATUS:', store.get_run(record['run_id'])['status'])
        events = [event['kind'] for event in store.list_events(record['run_id'])]
        print('EVENTS:', ' -> '.join(events))
        if 'resume_started' not in events or 'resume_completed' not in events:
            raise RuntimeError('Missing resume audit events')
        print('PASS: can_resume=True -> approval -> persisted checkpoint continued')


def status_demo():
    record = load_record()
    store = get_store()
    print('RUN:', store.get_run(record['run_id']))
    for event in store.list_events(record['run_id']):
        print(event['kind'], event['payload'])


def main():
    parser = argparse.ArgumentParser(description='Isolated deterministic Phase 4 recovery test')
    parser.add_argument('action', choices=('prepare', 'resume', 'status'))
    parser.add_argument('--yes', action='store_true', help='Explicitly approve demo recovery without prompt')
    args = parser.parse_args()
    if args.action == 'prepare':
        asyncio.run(prepare_demo())
    elif args.action == 'resume':
        asyncio.run(resume_demo(args.yes))
    else:
        status_demo()


if __name__ == '__main__':
    main()
