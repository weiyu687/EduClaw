"""
读取 Python 文件的代码

Author: Gongmin Wei
Date: 2026-04-08
"""
def extract_py(py_path: str) -> str:
    """从 Python 文件中提取代码"""
    try:
        with open(py_path, "r", encoding="utf-8", errors="replace") as f:
            code = f.read()
        return code
    except Exception as e:
        return f"Error: Failed to extract Python code from {py_path}. Error: {str(e)}"