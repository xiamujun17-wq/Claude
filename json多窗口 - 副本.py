import json
import os
import re
from datetime import datetime, timezone, timedelta

# ==========================================
# 🌟 在这里设置你的时区偏移量
# 北京时间 = UTC+8，写成 8
# 日本时间 = UTC+9，写成 9
# ==========================================
TIMEZONE_OFFSET = 8

# 输出的文件夹名称（脚本会自动创建）
OUTPUT_DIR = "翻译后的聊天记录"

# ---------- 1. 自动查找文件 ----------
def find_input_files():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    files = [f for f in os.listdir(script_dir) if f.endswith(('.json', '.txt'))]
    exclude = ['纯净聊天记录.txt', '完整聊天记录_含警告.txt']
    return sorted([f for f in files if f not in exclude])

input_files = find_input_files()
if not input_files:
    print("❌ 当前目录没有找到 .json 或 .txt 文件！")
    input("按回车键退出...")
    exit()

if len(input_files) == 1:
    JSON_FILE = input_files[0]
    print(f"📂 自动选用文件：{JSON_FILE}")
else:
    print("📂 找到多个文件，请选择要翻译的 JSON 文件：")
    for i, f in enumerate(input_files, 1):
        print(f"  {i}. {f}")
    choice = input("请输入编号：").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(input_files):
        JSON_FILE = input_files[int(choice)-1]
    else:
        print("❌ 无效输入，退出。")
        input("按回车键退出...")
        exit()
    print(f"📂 已选择：{JSON_FILE}")

# ---------- 2. 读取并解析 JSON ----------
try:
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
except Exception as e:
    print(f"❌ 读取 JSON 失败（如果是被截断的文件，请用完整文件重新导出）：{e}")
    input("按回车键退出...")
    exit()

# ---------- 3. 提取所有会话（窗口） ----------
conversations = []
if isinstance(data, list):
    conversations = data
elif isinstance(data, dict):
    # 兼容单个会话被包在字典里的情况
    for key in ['conversations', 'chat_messages', 'data']:
        if key in data and isinstance(data[key], list):
            conversations = data[key]
            break
    if not conversations:
        conversations = [data]

print(f"📬 找到 {len(conversations)} 个对话窗口，开始逐个翻译...")

# ---------- 4. 核心工具函数 ----------
def format_time(ts_str):
    if not ts_str:
        return "未知时间"
    try:
        if ts_str.endswith('Z'):
            ts_str = ts_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_tz = timezone(timedelta(hours=TIMEZONE_OFFSET))
        return dt.astimezone(local_tz).strftime("%Y-%m-%d %H:%M:%S")
    except:
        return ts_str.replace('T', ' ').split('.')[0].strip()

def extract_message_parts(msg):
    texts = []
    warnings = []
    content_list = msg.get('content', [])
    if isinstance(content_list, list):
        for item in content_list:
            if not isinstance(item, dict):
                continue
            if item.get('type') == 'text':
                t = item.get('text', '')
                if t:
                    texts.append(t)
            if item.get('type') == 'thinking':
                if 'summary' in item and item['summary']:
                    warnings.append(item['summary'])
                if 'summaries' in item and isinstance(item['summaries'], list):
                    for s in item['summaries']:
                        if isinstance(s, dict) and 'summary' in s and s['summary']:
                            warnings.append(s['summary'])
    if msg.get('summary'):
        warnings.append(msg['summary'])
    if not texts and msg.get('text'):
        texts.append(msg['text'])
    clean_texts = [t for t in texts if "This block is not supported" not in t]
    return "\n".join(clean_texts).strip(), warnings

# 确保输出文件夹存在
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------- 5. 逐个窗口处理 ----------
total_saved_files = 0

for conv_idx, conv in enumerate(conversations, 1):
    if not isinstance(conv, dict):
        continue
        
    raw_messages = conv.get('chat_messages', [])
    if not raw_messages:
        # 有些可能直接就是消息列表
        if 'sender' in conv and 'content' in conv:
            raw_messages = [conv]
        else:
            continue

    # 获取窗口名字
    conv_name = conv.get('name', '').strip()
    if not conv_name:
        conv_name = f"未命名窗口_{conv_idx}"
    
    # 清理名字里的非法字符，防止Windows无法创建文件
    safe_name = re.sub(r'[\\/*?:"<>|]', "_", conv_name)
    
    # 清洗当前窗口的数据
    cleaned_messages = []
    seen = set()
    
    for msg in raw_messages:
        if not isinstance(msg, dict):
            continue
            
        raw_time = msg.get('created_at') or msg.get('timestamp', '')
        time_str = format_time(raw_time)
        
        sender = msg.get('sender', '').lower()
        if sender in ['human', 'user']:
            role = '你'
        elif sender in ['assistant', 'ai', 'claude']:
            role = 'Claude'
        else:
            role = sender if sender else '未知'
        
        content, warnings = extract_message_parts(msg)
        if not content and not warnings:
            continue
            
        combined_content = ""
        if warnings:
            unique_warnings = list(dict.fromkeys(warnings))
            warning_str = "\n".join([f"⚠️ [system] {w}" for w in unique_warnings])
            combined_content += warning_str + "\n"
        if content:
            combined_content += content
        combined_content = combined_content.strip()

        # 双重去重
        fingerprint = f"{time_str}_{combined_content}"
        if fingerprint not in seen:
            seen.add(fingerprint)
            cleaned_messages.append(f"[{time_str}] {role}：\n{combined_content}")

    if not cleaned_messages:
        continue

    # 按时间排序当前窗口
    cleaned_messages.sort(key=lambda x: x.split(']')[0].replace('[', ''))
    
    # 保存文件
    output_filename = os.path.join(OUTPUT_DIR, f"{safe_name}.txt")
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write("\n\n".join(cleaned_messages))
    
    total_saved_files += 1
    print(f"  [{conv_idx}/{len(conversations)}] 已翻译窗口：'{conv_name}' -> 保存了 {len(cleaned_messages)} 条消息。")

print(f"\n✅ 全部完成！一共生成了 {total_saved_files} 个纯净 TXT 文件。")
print(f"📁 请去当前目录下的 '{OUTPUT_DIR}' 文件夹查看。")
input("\n按回车键退出...")