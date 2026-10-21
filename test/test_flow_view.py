from core.gui.flow_view import render_flow


def test_flow_view_pairs_each_step_with_its_own_input_output_and_integrity():
    detail={'number':4,'goal':'整理报告','completed':1,'total':2,'status':'running',
            'steps':[{'number':1,'tool':'public_search','arguments':{'query':'AI'},'status':'completed','dependencies':[]},
                     {'number':2,'tool':'write_text_file','arguments':{'path':'report.md'},'status':'waiting','dependencies':[1]}],
            'results':[{'step':1,'status':'completed','summary':'找到两条来源','digest':'abc','intact':True,'truncated':False}]}
    view=render_flow(detail)
    assert '01  public_search · 已完成' in view
    assert '"query": "AI"' in view and '找到两条来源' in view
    assert '02  write_text_file · 等待前序步骤' in view
    assert '输出：尚未保存' in view
    detail['results'][0]['intact']=False
    assert '结果需核查' in render_flow(detail)
