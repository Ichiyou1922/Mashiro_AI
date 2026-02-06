from datetime import date, datetime, timedelta, timezone
import re

def get_time() -> str:
    now = str(datetime.now())
    ptn = re.compile(r'(\d{2}):(\d{2})')
    if result := ptn.search(now):
        return f"現在時刻は{result.group(1)}時{result.group(2)}分です。"
    else:
        print("時刻の取得に失敗しました")
        return "時刻の取得に失敗しました"

def get_date() -> str:
    today = str(datetime.today())
    ptn = re.compile(r'(\d{4})-(\d{2})-(\d{2})')
    if result := ptn.search(today):
        return f"今日は{result.group(1)}年{result.group(2)}月{result.group(3)}日です。"
    else:
        print("日付の取得に失敗しました")
        return "日付の取得に失敗しました。"