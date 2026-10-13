# 多文件长流程测试

全部数据均为合成样本。挂载 project-audit、data-quality 技能，以及 extract_csv、extract_json、extract_jsonl、extract_text、profile_csv、run_python_code 工具。

复制同目录的任务测试文本.txt 到 GUI；其中路径适用于 D:\wgm\EduClaw，其他安装目录需替换。逐步审批 5 次读取和 3 次代码执行。

期望：净支出合计 540、预算合计 570；A 项目超支 10；note 缺失 1 条，无完全重复行。
