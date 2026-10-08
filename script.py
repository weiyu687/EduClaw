# generate_tree.py
import os

def generate_directory_tree(root_path: str, ignore_dirs: list[str] = None, prefix: str = "") -> str:
    """
    递归生成目录树字符串
    :param root_path: 根目录路径
    :param ignore_dirs: 需要忽略的文件夹名
    :param prefix: 树形前缀缩进
    :return: 目录树文本
    """
    if ignore_dirs is None:
        ignore_dirs = [".git", "__pycache__", "venv", ".venv", ".idea", ".vscode", "build", "dist"]

    tree_text = ""
    # 获取当前目录下所有条目，文件夹放前面，文件在后
    entries = os.listdir(root_path)
    dirs = []
    files = []
    for entry in entries:
        full_path = os.path.join(root_path, entry)
        if os.path.isdir(full_path):
            if entry not in ignore_dirs:
                dirs.append(entry)
        else:
            files.append(entry)
    items = dirs + files

    for idx, name in enumerate(items):
        full_path = os.path.join(root_path, name)
        is_last = (idx == len(items) - 1)
        connector = "└── " if is_last else "├── "
        tree_text += prefix + connector + name + "\n"

        if os.path.isdir(full_path):
            new_prefix = prefix + ("    " if is_last else "│   ")
            tree_text += generate_directory_tree(full_path, ignore_dirs, new_prefix)
    return tree_text


if __name__ == "__main__":
    # ========== 在这里修改你的项目根目录 ==========
    project_root = r"."  # "." 代表当前脚本所在目录；可以写绝对路径 r"D:/code/myproj"
    # ============================================

    tree = generate_directory_tree(project_root)
    out_content = f"# Project Directory Tree\n```\n{tree}```"

    # 控制台打印
    print(tree)
    # 写入markdown文件
    with open("directory_tree.md", "w", encoding="utf-8") as f:
        f.write(out_content)
    print("\n✅ 目录树已保存到 directory_tree.md")
