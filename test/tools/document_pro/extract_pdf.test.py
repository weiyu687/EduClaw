"""
测试 tool: extract_pdf 提取 pdf 内容

Author: Gongmin Wei
Date: 2026-04-05
"""
import json
import pdfplumber


def extract_pdf(pdf_path: str) -> str:
    """
    从 PDF 文件中提取内容 (文本 + 表格)
    :param pdf_path: PDF 文件路径
    :return: PDF 文件内容
    """
    content = {
        "total_pages": 0,
        "pages": []
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            content["total_pages"] = len(pdf.pages)
            for page_num, page in enumerate(pdf.pages, 1):
                page_content = {
                    "page_num": page_num,
                    "text": page.extract_text() or "",
                    "tables": []
                }

                try:
                    tables = page.extract_tables()
                    for table in tables:
                        rows = [[str(c).strip() if c else "" for c in row] for row in table]
                        md_table = []
                        for i, row in enumerate(rows):
                            line = "| " + " | ".join(row) + " |"
                            md_table.append(line)
                            if i == 0:
                                md_table.append("|" + "|".join(["---"] * len(row)) + "|")
                        page_content["tables"].append("\n".join(md_table))
                except Exception:
                    pass

                content["pages"].append(page_content)
    except Exception as e:
        return json.dumps({"error": f"PDF 文件读取失败 {e}"}, ensure_ascii=False, indent=2)

    return json.dumps(content, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    pdf_content = extract_pdf("./test_data/dual_page_with_tables.pdf")
    print(pdf_content)