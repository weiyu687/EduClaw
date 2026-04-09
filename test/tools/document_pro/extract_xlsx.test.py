"""
测试 tool: extract_xlsx 提取 xlsx 文件内容
"""
import pandas as pd
from typing import Union, Literal


def extract_xlsx(
        xlsx_path: str,
        sheet_name: Union[str, int] = 0,
        max_rows: int = 20,
        mode: Literal["single", "multi"] = "single"
) -> str:
    """
    提取 Excel (.xlsx) 文件内容。

    :param xlsx_path: 文件路径
    :param sheet_name: [仅在 single 模式下有效] 工作表名称或索引，默认为第一张表
    :param max_rows: 每张表返回的最大行数，防止 token 溢出
    :param mode: "single" 读取指定工作表, "multi" 读取文件中所有工作表
    """
    try:
        xl = pd.ExcelFile(xlsx_path)
        all_sheet_names = xl.sheet_names

        def process_sheet(df: pd.DataFrame, name: str) -> str:
            total_rows = len(df)
            columns = df.columns.tolist()
            df_preview = df.head(max_rows)
            markdown_table = df_preview.to_markdown(index=False)

            content = (
                f"--- 工作表: {name} ---\n"
                f"总行数: {total_rows}, 总列数: {len(columns)}\n"
                f"列名: {', '.join(map(str, columns))}\n\n"
                f"{markdown_table}\n"
            )
            if total_rows > max_rows:
                content += f"（已省略 {total_rows - max_rows} 行数据）\n"
            return content

        if mode == "single":
            df = pd.read_excel(xl, sheet_name=sheet_name)
            actual_name = sheet_name if isinstance(sheet_name, str) else all_sheet_names[sheet_name]
            result = f"文件路径: {xlsx_path}\n" + process_sheet(df, actual_name)

        else:
            result = f"文件路径: {xlsx_path}\n"
            result += f"检测到 {len(all_sheet_names)} 个工作表: {', '.join(all_sheet_names)}\n\n"

            for name in all_sheet_names:
                df = pd.read_excel(xl, sheet_name=name)
                result += process_sheet(df, name) + "\n"

        return result

    except Exception as e:
        return f"读取 Excel 文件时出错: {str(e)}"


if __name__ == "__main__":
    print(extract_xlsx("test_data/test.xlsx", mode="single", sheet_name=0))
    print(extract_xlsx("test_data/test.xlsx", mode="multi"))
