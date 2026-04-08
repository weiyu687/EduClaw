"""
测试 tool: get_all_files 获取指定文件夹下的所有文件的绝对路径、

Author: Gongmin Wei
Date: 2026-04-08
"""
import os


def get_all_files(folder_path: str) -> str:
    """获取指定文件夹下的所有文件的绝对路径"""
    if not os.path.exists(folder_path):
        return f"文件夹不存在: {folder_path}"

    if not os.path.isdir(folder_path):
        return f"路径不是一个目录: {folder_path}"

    file_paths = []
    try:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.abspath(os.path.join(root, file))
                file_paths.append(file_path)
    except PermissionError as e:
        return f"没有权限访问文件夹或其子目录: {e}"

    return "\n".join(file_paths)


if __name__ == "__main__":
    print(get_all_files("./document_pro"))