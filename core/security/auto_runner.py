"""Advance only steps explicitly allowed by current low-risk policy."""
from core.security.workspace_policy import automatic
from core.security.read_step_service import ReadStepService
from core.security.tool_step_service import ToolStepService
from core.security.multi_step_graph import READ_ARGS

async def advance(service,session,number,client):
    for _ in range(12):
        with service.stores(session) as (context,life):
            state=service.choose(context,session,number)
            if state['status']!='running' or life.ledger.control(session,state['task_id'])!='active':return
            step=state['steps'][state['index']]
            if not automatic(step['tool'],step['arguments'],session):return
            base=service.code_service(context,life)
            handler=base if step['tool']=='run_python_code' else ReadStepService(base) if step['tool'] in READ_ARGS else ToolStepService(base)
            review=handler.preview(session,state['task_id'])
            # Recheck resolved parameters immediately before obtaining the operation lock.
            args={'code':review['code']} if step['tool']=='run_python_code' else review.get('arguments',step['arguments'])
            if not automatic(step['tool'],args,session):return
            if step['tool'] in READ_ARGS:
                await handler.execute(session,state['task_id'],review['digest'],client,approved=False)
            else:await handler.execute(session,state['task_id'],review['digest'],client,approved=False)
