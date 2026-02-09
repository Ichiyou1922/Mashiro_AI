import sys 
import os
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from memory.memory_store import MemoryStore
from memory.reflection import ReflectionManager

# instance
print("===Step1 : MemoryStore初期化===")
memory_store = MemoryStore()

# add_memory
print("===Step2 : add_memoryのテスト===")
timestamp = memory_store.add_memory(
    text="テスト",
    user_id=1234567,
    user_name="test",
    role="user"
)
print(timestamp)

# get_pending_evaluation()
print("===Step3 : get_pending_evaluation()のテスト===")
pending_results = memory_store.get_pending_evaluation(limit=5)
print(pending_results)

# evaluate_importance()
print("===Step4 : evaluate_importance()のテスト===")
try:
    memory_store.evaluate_importance()
    print("importanceの更新が完了")
except Exception as e:
    print(f"evaluate_importance() error: {e}")

print("===Step5 : importance合計のテスト===")
importance_sum = memory_store.get_importance_sum(since=0)
print(importance_sum)

print("===Step6 : perform_reflectionのテスト===")
print("ReflectionManagerのインスタンス化")
reflection_manager = ReflectionManager()
print("reflectionの実行")
reflection_data = reflection_manager.perform_reflection()
print(reflection_data)


print("終了")
