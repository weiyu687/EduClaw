"""One reviewed Python step in an isolated process; never accepts raw code."""
import argparse
import asyncio
import json
import sys

from core.gui.service import DashboardService
from core.security.code_step_service import CodeStepService
from core.security.dag_dependencies import DagStore


async def execute(directory, payload):
    from core.mcp.client import MCPClient
    service = DashboardService(directory)
    session, number = payload['session'], payload['number']
    with service.stores(session) as (context, life):
        state = service.choose(context,session,number)
        task = state['task_id']
        client = MCPClient()
        steps = CodeStepService(context.flow,life.ledger,life.results,
            DagStore(service.directory/'educlaw_dag_plans.sqlite3'),context.replans,life)
        try:
            # Validate before starting the transport; validate again under the OS lock.
            if steps.preview(session,task)['digest'] != payload['digest']:
                raise PermissionError('已确认的任务或代码发生变化。')
            async with asyncio.timeout(90):
                try:
                    await client.connect()
                    await steps.execute(session,task,payload['digest'],client)
                finally:
                    await client.disconnect()
        except Exception as exc:
            life.failure(session,task,state['index'],exc)
            raise


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',required=True)
    args=parser.parse_args()
    payload=json.loads(sys.stdin.read(8193))
    if not isinstance(payload,dict) or set(payload)!={'session','number','digest'}:
        raise ValueError('Invalid execution identity')
    asyncio.run(execute(args.data_dir,payload))


if __name__=='__main__': main()
