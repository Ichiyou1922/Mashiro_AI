from datasets import load_dataset
import json
from pathlib import Path


class CasualConversationDownloader:
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def download(self) -> list:
        """HuggingFaceからダウンロードして整形"""
        # >>> from datasets import load_dataset
        # >>> dataset = load_dataset("SohamGhadge/casual-conversation", split="train")
        # dataset.features
        # 以上で形式を確認
        # {'Unnamed: 0': Value('int64'), 'question': Value('string'), 'answer': Value('string')}
        ds = load_dataset("SohamGhadge/casual-conversation", split="train")
        list_data = []
        '''
        for i in ds['Unnamed: 0']:
            data = ds[i]
            list_data.append({
                "instruction": data['question'],
                "response": data['answer']
            })
        '''
        for row in ds:
            list_data.append({
                "instruction": row['question'],
                "response": row['answer']
            })
        return list_data
    
    def save(self, data: list, filename: str = 'casual_conversation.json'):
        with open(f"{self.output_dir}/{filename}", mode="w") as f:
            json.dump(data, f, indent=2)

    def run(self):
        """実行"""
        data = self.download()
        self.save(data)
        print(f"saved {len(data)} conversations")
    


'''
class SHPDownloader:
    def __init__(self, output_dir: str, limit: int = 5000):
        """
        __init__ の Docstring

        :param output_dir: 保存先ディレクトリ
        :type output_dir: str
        :param limit: 最大取得件数
        :type limit: int
        """
        self.output_dir = output_dir
        self.limit = limit
        # dataset = load_dataset("stanfordnlp/SHP", split="train")
        def download(self) -> list:
            pass

        def filter(self, data: list, min_score: int = 5, max_length: int = 500):
            pass

        def save(self, data: list, filename: str = "shp_extracted.json"):
            """JSONとして保存"""
            pass

        def run(self):
            """全体の実行"""
            data = self.download()
            data = self.filter(data)
            self.save(data)
'''