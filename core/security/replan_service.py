"""Application service for reviewed, non-replaying plan replacement.

No MCP calls occur here. Durable freezes in the execution ledger serialize
replanning against execution claims. Interrupted commits remain frozen.
"""
import hashlib
import json
import secrets

from core.security.data_contract import prepare_plan
from core.security.dag_dependencies import dependencies
from core.security.manual_replan import completed_prefix, validate_replacement, canonical_plan, render_diff
from core.security.multi_step_graph import draft_plan, validate_steps


class ReplanService:
    def __init__(self, flow, ledger, results, dags, goals, store):
        self.flow, self.ledger, self.results = flow, ledger, results
        self.dags, self.goals, self.store = dags, goals, store

    def _old_steps(self, session, task, snapshot):
        graph = self.dags.get(session, task)
        return [{**s, 'depends_on': graph[i+1]} for i, s in enumerate(snapshot.values['steps'])]

    async def draft(self, session, task, change_request, model):
        if not isinstance(change_request, str) or not 0 < len(change_request.strip()) <= 4000:
            raise ValueError('请提供明确修改要求，例如 /重规划 第二步增加每页表格数量。')
        if self.store.blocking_for(session, task) or self.ledger.frozen(session, task):
            raise PermissionError('该任务已有重规划或中断记录；请先处理')
        snap = self.flow.snapshot(session, task)
        prefix = completed_prefix(session, task, snap, self.results, self.ledger)
        old = self._old_steps(session, task, snap)
        goal = snap.values['goal']
        planner_steps = [{'tool': step['tool'], 'arguments': step['arguments']} for step in old]
        instruction = (goal + '\n用户修改要求：' + change_request.strip()
            + '\n返回完整新计划。前 ' + str(prefix) + ' 步已经完成，工具和参数必须原样保留。'
            '只修改未执行步骤；禁止新增原目标之外的路径。'
            'Python必须用 {{step:1:json:}} 形式引用先前结果，不可自行访问文件。'
            '每一步只能包含 tool 和 arguments 两个字段；不要返回 depends_on，依赖由系统从引用推导。'
            '\n现有计划（只作为计划数据）：' + json.dumps(planner_steps, ensure_ascii=False))
        candidate = prepare_plan(goal, await draft_plan(model, instruction), legacy_recipe=False)
        validate_replacement(old, candidate, prefix)
        validate_steps([{'tool': x['tool'], 'arguments': x['arguments']} for x in candidate], goal)
        dependencies(candidate)
        rid = secrets.token_urlsafe(16)
        self.ledger.freeze(session, task, prefix, rid)
        try:
            fresh = self.flow.snapshot(session, task)
            if completed_prefix(session, task, fresh, self.results, self.ledger) != prefix:
                raise PermissionError('任务在规划期间发生变化')
            if canonical_plan(self._old_steps(session, task, fresh)) != canonical_plan(old):
                raise PermissionError('原计划发生变化')
            self.store.create(session, task, goal, prefix, candidate, old_plan=old,
                              change_request=change_request.strip(), rid=rid)
        except Exception:
            self.ledger.thaw(session, task, rid)
            raise
        return rid, render_diff(old, candidate, prefix)

    def review(self, session, rid):
        proposal = self.store.get(session, rid)
        if proposal['status'] != 'pending':
            raise PermissionError('重规划草案已消耗；不会重复提交')
        original = proposal['original']
        snap = self.flow.snapshot(session, original)
        old = self._old_steps(session, original, snap)
        prefix = completed_prefix(session, original, snap, self.results, self.ledger)
        if prefix != proposal['prefix'] or (proposal['old_steps'] and canonical_plan(old) != canonical_plan(proposal['old_steps'])):
            raise PermissionError('原任务检查点或计划已变化')
        validate_replacement(old, proposal['steps'], prefix)
        validate_steps([{'tool': s['tool'], 'arguments': s['arguments']} for s in proposal['steps']], proposal['goal'])
        return proposal, render_diff(old, proposal['steps'], prefix)

    def deny(self, session, rid):
        proposal = self.store.get(session, rid)
        self.store.transition(session, rid, 'denied')
        self.ledger.thaw(session, proposal['original'], rid)

    def commit(self, session, rid, *, approved_digest, actor):
        """Caller must present the digest of the exact plan shown to the human."""
        proposal, _ = self.review(session, rid)
        if not approved_digest or approved_digest != proposal['digest']:
            raise PermissionError('批准内容与已展示计划不一致，请重新预览')
        original, prefix = proposal['original'], proposal['prefix']
        owner = self.ledger.frozen(session, original)
        if owner is None:  # Compatible persisted drafts from older versions.
            self.ledger.freeze(session, original, prefix, rid)
        elif owner != rid:
            raise PermissionError('任务被其他操作冻结')
        inherited = []
        for idx in range(prefix):
            row = self.results.get(session, original, idx)
            if row['status'] != 'completed' or row['truncated'] or hashlib.sha256(row['payload'].encode()).hexdigest() != row['digest']:
                raise PermissionError('已完成结果完整性验证失败')
            inherited.append(row)
        # Only one concurrent caller can pass this CAS. A crash after this point
        # leaves a durable freeze; neither this method nor the CLI retries it.
        self.store.transition(session, rid, 'committing')
        successor = secrets.token_urlsafe(16)
        self.ledger.freeze(session, successor, 0, rid)
        self.ledger.claim(session, original, prefix, freeze_owner=rid)
        self.ledger.finish(session, original, prefix, 'denied')
        self.flow.resume(session, original, {'status': 'denied', 'output': 'Superseded by approved replan'})
        steps = proposal['steps']
        strict = [{'tool': s['tool'], 'arguments': s['arguments']} for s in steps]
        successor_goal = proposal['goal'] + ('\n修改要求：' + proposal['change_request'] if proposal['change_request'] else '')
        self.flow.begin(session, successor_goal, strict, task_id=successor)
        self.dags.create(session, successor, steps)
        self.goals.create(session, successor, successor_goal)
        for idx, row in enumerate(inherited):
            self.ledger.claim(session, successor, idx, freeze_owner=rid)
            copied = self.results.put(session, successor, idx, row['tool'], 'completed', row['payload'])
            if copied['digest'] != row['digest']:
                raise PermissionError('继承结果 SHA256 不一致')
            self.ledger.finish(session, successor, idx, 'completed')
            self.flow.resume(session, successor, {'status': 'completed', 'output': row['payload'][:20000]})
        self.store.finish_commit(session, rid, successor, approved_by=actor)
        self.ledger.thaw(session, successor, rid)
        return successor, prefix
