---
name: homework-grader
version: 1.0.0
description: 批改学生作业
Author: Gongmin Wei
Date: 2026-04-08
---

# Homework Grader - 批改学生作业

## 工作流

### 情景一：Python 课程作业批改
针对用户需要对Python 课程作业进行批改，通常不止一份作业，
用户需要提供包含多个 Python 文件的目录，
同时提供题目和尽可能详细的评分标准
```
1. 若用户没有提供运行结果，则使用工具 run_python_code 获取正确运行结果
2. 使用工具 get_all_files 获取所有待执行的 Python 文件路径
3. 使用工具 run_python_file 运行所有 Python 文件， 记录运行情况（能否运行，结果是否正确...）
4. 若用户的评分标准里要求代码格式规范，使用工具 extract_py 读取代码
5. 最后向用户汇报作业完成情况，得分以及评分依据
```