from openai import OpenAI

# 初始化客户端
client = OpenAI(base_url="http://localhost:8000/v1",api_key="null")

response = client.chat.completions.create(
  model="qwen3",
  messages=[
    {"role": "system", "content": "你是一个严谨的助手。"},
    {"role": "user", "content": "请解释一下什么是量子纠缠。"}
  ],
  temperature=0.7,
  stream=True,
  max_tokens=500
)

for chunk in response:
    print(chunk.choices[0].delta.content, end="")

# print(response.choices[0].message.content)