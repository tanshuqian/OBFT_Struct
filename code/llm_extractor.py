import json
import os
import time
from openai import OpenAI
from utils import clean_json_string

MODEL_PATH = "/root/autodl-tmp/model/Qwen/Qwen3-14B-FP8/"
SYS_PROMPT_FILE = os.path.join(os.path.dirname(__file__), "..", "prompt", "extract_prompt_up_0604.txt")
USER_PROMPT_FILE = os.path.join(os.path.dirname(__file__), "..", "prompt", "user_prompt.txt")


def extract_json_array(raw_str: str) -> list:
    cleaned_str = clean_json_string(raw_str)
    try:
        start = cleaned_str.find('[')
        end = cleaned_str.rfind(']')
        if start != -1 and end != -1:
            json_str = cleaned_str[start:end + 1]
            return json.loads(json_str)
        return []
    except json.JSONDecodeError:
        print(f"    [警告] JSON 解析严重失败，原始文本: {cleaned_str[:50]}...")
        return []


class LLMExtractor:
    def __init__(self, base_url: str | None = None, model_name: str | None = None, print_raw: bool = False):
        base_url = base_url or os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
        model_name = model_name or os.getenv("VLLM_MODEL_NAME", "qwen3")

        print(f"🚀 正在连接到 vLLM API 服务 ({base_url}) ...")
        self.client = OpenAI(
            base_url=base_url,
            api_key="none"
        )
        self.model_name = model_name
        self.print_raw = print_raw
        with open(SYS_PROMPT_FILE, 'r', encoding='utf-8') as f:
            self.sys_prompt = f.read()

    def ping(self) -> bool:
        try:
            self.client.models.list()
            return True
        except Exception:
            return False

    def extract(self, chunk_text: str, return_raw: bool = False) -> tuple:

        with open(USER_PROMPT_FILE, 'r', encoding='utf-8') as f:
            prompt_template = f.read()

        user_prompt = prompt_template.replace("{chunk_text}", chunk_text.strip())

        messages = [
            {"role": "system", "content": self.sys_prompt},
            {"role": "user", "content":user_prompt}
        ]

        start_time = time.time()

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0.0,
            max_tokens=512,
            extra_body={"stop_token_ids": [151645]}
        )

        raw_output = response.choices[0].message.content
        inference_time = time.time() - start_time


        parsed_data = extract_json_array(raw_output)
        if return_raw:
            return parsed_data, inference_time, raw_output
        return parsed_data, inference_time




if __name__ == '__main__':
    import data
    llm = LLMExtractor()
    s = """
D：双下肢有没有水肿？
P：没有，脚不肿。
D：宫高34cm，腹围112cm。估计胎儿体重在3.6kg左右。
P：宝宝还挺胖的。
"""
    s1 = """D：您好，请坐。今天过来主要是做什么检查？
P：医生你好，我到现在停经已经37周加2天了，快到预产期了，过来做个常规产检。
D：末次月经是哪天？
P：是2月9号。"""
    s2 = """D：好的，我来给你做个检查。先量个血压，122/60mmHg，心率68次/分，都正常。
P：那就好，这个胀痛会不会是要早产了呀？
D：先别急，我看看下肢有没有水肿。
P：好的。"""
    s3 = """D：您好，请坐。今天过来主要是哪里不舒服？
P：医生你好，我肚子一阵一阵地痛，大概痛了一个多小时了。
D：现在怀孕多少周了？
P：停经39周加3天了，快到预产期了。
    """
    s4 = """D：胎位是LOT，也就是左枕横位，头先露，胎位很正常。
P：那就是头朝下对吧？
D：对的。胎心音144次/分，也很正常。估计胎儿体重在2991g左右。
P：大概6斤不到，那还算标准吧？    
    """
    s5 = """D：我给您量一下肚子。宫高35cm，腹围102cm。
P：宝宝大小正常吗？
D：大小还可以。胎心是144次/分，很正常。
P：那胎位正吗？"""
    for l in s5.split("--"):
        chunk = l.strip()
        if not chunk:
            continue
        parsed, inference_time, raw = llm.extract(chunk, return_raw=True)
        print("--- 原文片段 ---")
        print(chunk)
        print("--- 解析结果（每个 JSON 对象单行输出） ---")
        if not parsed:
            print("[]")
        else:
            # 每个对象单行输出，去掉多余空格以更紧凑（中文保留）
            for obj in parsed:
                print(json.dumps(obj, ensure_ascii=False, separators=(',', ':')))
        print(f"(inference_time={inference_time:.3f}s)\n")
