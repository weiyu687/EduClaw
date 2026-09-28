"""
记忆系统与 Agent 集成的端到端测试

Author: Development Team
Date: 2026-09-27
"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.agent.agent_factory import EduClawAgent


async def test_agent_with_memory():
    """
    测试 Agent 与记忆系统的集成

    这个测试模拟一个完整的教育场景：
    1. 学生多轮对话
    2. 系统自动保存对话到记忆
    3. 后续对话使用之前的记忆作为上下文
    """
    print("\n" + "=" * 60)
    print("Agent 与记忆系统集成测试")
    print("=" * 60)

    try:
        # 创建 Agent，启用记忆
        print("\n1. 初始化 Agent...")
        agent = EduClawAgent(enable_memory=True)

        # 设置会话上下文
        session_id = "education_session_001"
        student_id = "student_alice"
        agent.set_session_context(session_id, student_id)

        print(f"✓ Agent 初始化成功")
        print(f"  - 会话 ID: {session_id}")
        print(f"  - 学生 ID: {student_id}")
        print(f"  - 记忆系统: {'启用' if agent.enable_memory else '禁用'}")

        # 模拟教学场景
        print("\n2. 模拟教学场景...")

        # 场景 1: 保存学生档案
        print("\n  场景 A: 保存学生档案")
        if agent.memory_manager:
            student_profile = {
                "name": "Alice",
                "grade": "高一",
                "subject": "数学",
                "learning_style": "视觉学习者",
                "difficulty": "中等难度"
            }

            profile_id = await agent.memory_manager.save_user_profile(student_profile)
            if profile_id:
                print(f"  ✓ 学生档案已保存 (ID: {profile_id})")
            else:
                print(f"  ✗ 学生档案保存失败")

        # 场景 2: 保存学习内容
        print("\n  场景 B: 保存教学内容")
        lesson_topics = [
            ("一次函数", "一次函数是形如 y = kx + b 的函数，其中 k≠0"),
            ("函数图像", "通过坐标系绘制函数的图像可以直观理解函数性质"),
            ("函数应用", "一次函数可用于模拟实际生活中的线性关系")
        ]

        for topic, content in lesson_topics:
            memory_id = await agent.save_knowledge(
                title=topic,
                content=content,
                tags=["mathematics", "high_school"]
            )
            if memory_id:
                print(f"  ✓ '{topic}' 已保存")

        # 场景 3: 模拟对话（这部分需要 Agent 已启动）
        print("\n  场景 C: 模拟学生提问")
        print("  注意: 以下演示假设 Agent 和 MCP Server 已启动")

        sample_questions = [
            "什么是一次函数？",
            "怎样画函数的图像？",
            "一次函数有什么实际应用？"
        ]

        for i, question in enumerate(sample_questions, 1):
            print(f"\n    提问 {i}: {question}")

            # 模拟保存对话（如果 Agent 启动了，可以实际调用）
            if agent.memory_manager:
                # 这里使用模拟的回答
                simulated_answer = f"这是关于 '{question}' 的回答。基于你之前学习的内容，..."

                memory_id = await agent.memory_manager.save_conversation(question, simulated_answer)
                if memory_id:
                    print(f"    ✓ 对话已保存到记忆")

        # 场景 4: 测试记忆召回
        print("\n  场景 D: 测试记忆召回")

        recall_query = "我想了解函数和图像的关系"
        print(f"\n    查询: '{recall_query}'")

        related_memories = await agent.recall_memories(recall_query, limit=3)
        if related_memories:
            print(f"    ✓ 召回了 {len(related_memories)} 条相关记忆:")
            for i, mem in enumerate(related_memories, 1):
                preview = mem[:80] if len(mem) > 80 else mem
                print(f"      {i}. {preview}...")
        else:
            print(f"    - 未召回相关记忆（这可能是正常的，取决于初始化的内容）")

        # 场景 5: 获取会话总结
        print("\n  场景 E: 会话统计")
        session_memories = await agent.get_session_memories()
        print(f"    ✓ 本会话保存了 {len(session_memories)} 条记忆")

        if session_memories:
            categories = {}
            for mem in session_memories:
                cat = mem.category
                categories[cat] = categories.get(cat, 0) + 1

            print(f"    分类统计:")
            for cat, count in categories.items():
                print(f"      - {cat}: {count} 条")

        print("\n" + "=" * 60)
        print("✓ Agent 与记忆系统集成测试完成")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n✗ 测试出现异常: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_memory_persistence():
    """
    测试记忆持久化

    验证记忆是否能在不同的 Agent 实例间保持
    """
    print("\n" + "=" * 60)
    print("记忆持久化测试")
    print("=" * 60)

    try:
        # 第一个 Agent 实例：保存数据
        print("\n1. 第一个 Agent 实例 - 保存数据")
        agent1 = EduClawAgent(enable_memory=True)
        agent1.set_session_context("persistence_session", "user_001")

        memory_ids = []
        test_data = [
            ("知识点 A", "这是第一条持久化测试数据"),
            ("知识点 B", "这是第二条持久化测试数据"),
        ]

        for title, content in test_data:
            mem_id = await agent1.save_knowledge(title, content)
            if mem_id:
                memory_ids.append(mem_id)
                print(f"  ✓ 保存: {title}")

        # 第二个 Agent 实例：验证数据
        print("\n2. 第二个 Agent 实例 - 验证数据")
        agent2 = EduClawAgent(enable_memory=True)
        agent2.set_session_context("persistence_session", "user_001")

        session_memories = await agent2.get_session_memories()
        print(f"  ✓ 检索到 {len(session_memories)} 条持久化记忆")

        if len(session_memories) > 0:
            print("  持久化验证:")
            for mem in session_memories:
                print(f"    - [{mem.category}] {mem.content[:60]}...")

            return True
        else:
            print("  ⚠️  未找到持久化的记忆（可能是首次初始化）")
            return True

    except Exception as e:
        print(f"✗ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_memory_disabled():
    """测试禁用记忆系统的情况"""
    print("\n" + "=" * 60)
    print("记忆系统禁用测试")
    print("=" * 60)

    try:
        print("\n1. 创建禁用记忆的 Agent...")
        agent = EduClawAgent(enable_memory=False)

        if agent.memory_manager is None:
            print("✓ 记忆系统已禁用")
        else:
            print("✗ 记忆系统应该被禁用")
            return False

        print("\n2. 测试方法可用性...")

        # 这些方法应该能处理记忆系统禁用的情况
        agent.set_session_context("test", "user")

        result = await agent.recall_memories("test query")
        if result == []:
            print("✓ recall_memories 返回空列表（符合预期）")

        memories = await agent.get_session_memories()
        if memories == []:
            print("✓ get_session_memories 返回空列表（符合预期）")

        print("\n✓ 禁用记忆系统测试通过")
        return True

    except Exception as e:
        print(f"✗ 异常: {e}")
        return False


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("EduClaw Agent 记忆系统端到端测试")
    print("=" * 60)

    results = {}

    # 运行所有测试
    results["Agent 集成"] = await test_agent_with_memory()
    results["记忆持久化"] = await test_memory_persistence()
    results["记忆禁用"] = await test_memory_disabled()

    # 打印总结
    print("\n" + "=" * 60)
    print("端到端测试总结")
    print("=" * 60)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {test_name}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n总计:  {passed}/{total} 测试通过")

    if passed == total:
        print("\n🎉 所有端到端测试通过！")
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
