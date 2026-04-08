---
name: sandbox
version: 1.0.0
description: Python 执行技能
Author: Gongmin Wei
Date: 2026-04-08
---

# Sandbox - Python 执行技能

## 工作流

### 情景一：代码片段执行
用户问题适用于**计算、逻辑校验、数据处理**等场景，或用户直接给出代码片段需要执行。
```
run_python_code
```

### 情景二：本地 Python 文件执行
用户需要运行本地 Python 文件，直接执行文件内容。
```
run_python_file
```

### 情景三：代码报错修复与运行
用户本地代码运行报错时，先询问用户是否需要修复，修复后执行代码
```
extract_py → run_python_code
```