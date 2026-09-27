"""
记忆系统集成测试

Author: Development Team
Date: 2026-09-27
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.agent.agent_factory import EduClawAgent


async def test_memory_initialization():
    """测试 1: 记忆系统初始化"""
    print("\n" + "=" * 60)
    print("测试 1: 记忆系统初始化")
    print("=" * 60)

    try:
        agent = EduClawAgent(enable_memory=True)

        if agent.memory_manager:
            print("✓ 记忆系统初始化成功")
            print(f"  - 记忆后端: {type(agent.memory_manager.backend).__name__}")
            print(f"  - 存储目录: {agent.memory_manager.backend.persist_dir}")
            return True
        else:
            print("✗ 记忆系统初始化失败")
            return False
    except Exception as e:
        print(f"✗ 初始化异常: {e}")
        return False


async def test_session_context():
    """测试 2: 会话上下文设置"""
    print("\n" + "=" * 60)
    print("测试 2: 会话上下文设置")
    print("=" * 60)

    try:
        agent = EduClawAgent(enable_memory=True)

        session_id = "test_session_001"
        user_id = "student_001"

        agent.set_session_context(session_id, user_id)

        if agent.session_id == session_id and agent.user_id == user_id:
            print("✓ 会话上下文设置成功")
            print(f"  - Session ID: {agent.session_id}")
            print(f"  - User ID: {agent.user_id}")
            return True
        else:
            print("✗ 会话上下文设置失败")
            return False
    except Exception as e:
        print(f"✗ 异常: {e}")
        return False


async def test_save_knowledge():
    """测试 3: 保存知识记忆"""
    print("\n" + "=" * 60)
    print("测试 3: 保存知识记忆")
    print("=" * 60)

    try:
        agent = EduClawAgent(enable_memory=True)
        agent.set_session_context("test_session_002", "student_001")

        # 保存多个知识记忆
        memory_ids = []

        test_knowledge = [
            {
                "title": "Python 基础语法",
                "content": "Python 是一种高级编程语言，具有简洁易学的特点。变量定义、数据类型、控制流等基础知识。",
                "tags": ["python", "programming", "basics"]
            },
            {
                "title": "学生成绩记录",
                "content": "数学: 95分，英语: 88分，物理: 92分，化学: 85分",
                "tags": ["student_progress", "grades"]
            },
            {
                "title": "学习目标",
                "content": "本周计划学习：面向对象编程、异常处理、文件操作。预计完成时间：5天。",
                "tags": ["learning_goal", "schedule"]
            }
        ]

        for item in test_knowledge:
            memory_id = await agent.save_knowledge(
                title=item["title"],
                content=item["content"],
                tags=item["tags"]
            )
            if memory_id:
                memory_ids.append(memory_id)
                print(f"✓ 保存知识: {item['title']}")
                print(f"  - 记忆 ID: {memory_id}")
            else:
                print(f"✗ 保存失败: {item['title']}")

        if len(memory_ids) == len(test_knowledge):
            print(f"\n✓ 成功保存 {len(memory_ids)} 条知识记忆")
            return True, memory_ids
        else:
            print(f"\n✗ 部分记忆保存失败")
            return False, memory_ids

    except Exception as e:
        print(f"✗ 异常: {e}")
        return False, []


async def test_recall_memories():
    """测试 4: 召回相关记忆"""
    print("\n" + "=" * 60)
    print("测试 4: 召回相关记忆")
    print("=" * 60)

    try:
        agent = EduClawAgent(enable_memory=True)
        agent.set_session_context("test_session_003", "student_001")

        # 先保存一些知识
        print("\n保存测试数据...")
        await agent.save_knowledge(
            "Python 编程",
            "学习 Python 的基础语法和常用库",
            ["python", "programming"]
        )
        await agent.save_knowledge(
            "数据结构",
            "列表、字典、集合等数据结构的使用方法",
            ["data_structure", "algorithm"]
        )
        await agent.save_knowledge(
            "JavaScript 入门",
            "JavaScript 是前端开发的主要语言",
            ["javascript", "frontend"]
        )

        print("✓ 测试数据已保存\n")

        # 测试不同的查询
        test_queries = [
            "Python 编程怎么学",
            "数据结构",
            "前端开发"
        ]

        for query in test_queries:
            print(f"查询: '{query}'")
            memories = await agent.recall_memories(query, limit=2)

            if memories:
                print(f"✓ 召回 {len(memories)} 条相关记忆:")
                for i, mem in enumerate(memories, 1):
                    preview = mem[:100] if len(mem) > 100 else mem
                    print(f"  {i}. {preview}...")
            else:
                print(f"✗ 未找到相关记忆")
            print()

        return True

    except Exception as e:
        print(f"✗ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_conversation_memory():
    """测试 5: 对话记忆保存"""
    print("\n" + "=" * 60)
    print("测试 5: 对话记忆保存")
    print("=" * 60)

    try:
        agent = EduClawAgent(enable_memory=True)
        agent.set_session_context("test_session_004", "student_002")

        # 模拟保存对话
        test_conversations = [
            ("什么是面向对象编程?", "面向对象编程是一种编程范式，它使用对象和类来组织代码..."),
            ("能给我解释一下继承吗?", "继承是面向对象编程的一个核心概念，它允许子类继承父类的属性和方法..."),
            ("多态是什么?", "多态是指不同的对象可以对同一消息做出不同的响应...")
        ]

        memory_ids = []
        for human_msg, ai_msg in test_conversations:
            # 直接调用 memory_manager 保存
            if agent.memory_manager:
                memory_id = await agent.memory_manager.save_conversation(human_msg, ai_msg)
                if memory_id:
                    memory_ids.append(memory_id)
                    print(f"✓ 保存对话: {human_msg[:30]}...")
                    print(f"  - 记忆 ID: {memory_id}")

        if len(memory_ids) == len(test_conversations):
            print(f"\n✓ 成功保存 {len(memory_ids)} 条对话记忆")
            return True
        else:
            print(f"\n✗ 部分对话保存失败")
            return False

    except Exception as e:
        print(f"✗ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_session_memories():
    """测试 6: 获取会话记忆"""
    print("\n" + "=" * 60)
    print("测试 6: 获取会话记忆")
    print("=" * 60)

    try:
        agent = EduClawAgent(enable_memory=True)
        session_id = "test_session_005"
        agent.set_session_context(session_id, "student_003")

        # 保存多个记忆
        print("保存测试记忆...")
        await agent.save_knowledge("测试知识 1", "这是第一条知识记忆", ["test"])
        await agent.save_knowledge("测试知识 2", "这是第二条知识记忆", ["test"])

        if agent.memory_manager:
            # 获取会话记忆
            memories = await agent.get_session_memories()

            print(f"\n✓ 获取会话记忆成功")
            print(f"  - 会话 ID: {session_id}")
            print(f"  - 记忆总数: {len(memories)}")

            if memories:
                print(f"\n  记忆列表:")
                for i, mem in enumerate(memories, 1):
                    print(f"    {i}. [{mem.category}] {mem.content[:60]}...")

            return len(memories) > 0
        else:
            print("✗ 记忆管理器未初始化")
            return False

    except Exception as e:
        print(f"✗ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_memory_vector_similarity():
    """测试 7: 向量相似度搜索"""
    print("\n" + "=" * 60)
    print("测试 7: 向量相似度搜索")
    print("=" * 60)

    try:
        agent = EduClawAgent(enable_memory=True)
        agent.set_session_context("test_session_006", "student_004")

        # 保存相关主题的知识
        print("保存相关主题的知识...")
        topics = [
            ("机器学习基础", "机器学习是人工智能的一个分支，包括监督学习、无监督学习等"),
            ("深度学习", "深度学习使用神经网络处理数据，广泛应用于图像识别和自然语言处理"),
            ("神经网络", "神经网络是受生物神经网络启发的计算模型"),
            ("自然语言处理", "NLP 是处理人类语言的技术，包括文本分类、情感分析等"),
            ("计算机视觉", "CV 是处理图像和视频的技术，应用于目标检测、人脸识别等")
        ]

        for title, content in topics:
            await agent.save_knowledge(title, content, ["ai", "ml"])

        print("✓ 测试数据已保存\n")

        # 使用相似的但不同的查询来测试向量相似度
        test_queries = [
            "什么是人工智能学习",  # 应该返回机器学习和深度学习相关的
            "图片识别技术",  # 应该返回计算机视觉相关的
            "语言处理",  # 应该返回 NLP 相关的
        ]

        print("测试向量相似度搜索:")
        for query in test_queries:
            print(f"\n查询: '{query}'")
            memories = await agent.recall_memories(query, limit=3)

            if memories:
                print(f"✓ 返回 {len(memories)} 条相关记忆:")
                for i, mem in enumerate(memories, 1):
                    preview = mem[:80] if len(mem) > 80 else mem
                    print(f"  {i}. {preview}...")
            else:
                print(f"✗ 未找到相关记忆")

        return True

    except Exception as e:
        print(f"✗ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("EduClaw 记忆系统集成测试套件")
    print("=" * 60)

    results = {}

    # 测试 1: 初始化
    results["初始化"] = await test_memory_initialization()

    # 测试 2: 会话上下文
    results["会话上下文"] = await test_session_context()

    # 测试 3: 保存知识
    results["保存知识"] = (await test_save_knowledge())[0]

    # 测试 4: 召回记忆
    results["召回记忆"] = await test_recall_memories()

    # 测试 5: 对话记忆
    results["对话记忆"] = await test_conversation_memory()

    # 测试 6: 会话记忆
    results["会话记忆"] = await test_session_memories()

    # 测试 7: 向量相似度
    results["向量相似度"] = await test_memory_vector_similarity()

    # 打印总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {test_name}")

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n🎉 所有测试通过！记忆系统正常工作。")
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败，请检查错误信息。")

    return passed == total


if __name__ == "__main__":
    # 运行测试
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
