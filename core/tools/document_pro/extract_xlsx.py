"""
提取 xlsx 文件内容

Author: Gongmin Wei
Date: 2026-04-09
"""
import pandas as pd
from typing import Union


def extract_xlsx(
        xlsx_path: str,
        sheet_index: Union[int, str] = 0,  # 允许传入整数或字符串
) -> str:
    """
    提取 Excel (.xlsx) 文件内容
    :param xlsx_path: 文件路径
    :param sheet_index: 工作表序号(从0开始) 或 工作表名称
    """
    try:
        actual_sheet: Union[int, str] = sheet_index
        if isinstance(sheet_index, str):
            if sheet_index.isdigit():
                actual_sheet = int(sheet_index)

        xl = pd.ExcelFile(xlsx_path)

        if isinstance(actual_sheet, int):
            if actual_sheet >= len(xl.sheet_names):
                return f"错误：索引 {actual_sheet} 越界。该文件只有 {len(xl.sheet_names)} 个工作表。"
            display_name = xl.sheet_names[actual_sheet]
        else:
            display_name = actual_sheet

        df = pd.read_excel(xl, sheet_name=actual_sheet)

        total_rows = len(df)
        columns = df.columns.tolist()

        content = (
            f"文件路径: {xlsx_path}\n"
            f"--- 工作表: {display_name} ---\n"
            f"总行数: {total_rows}, 总列数: {len(columns)}\n"
            f"列名: {', '.join(map(str, columns))}\n\n"
            f"{df.to_markdown(index=False)}\n"
        )

        return content

    except Exception as e:
        return f"读取 Excel 失败: {str(e)}"