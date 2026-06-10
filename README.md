总体工作流概览
输入会话解析 → 2) 片段切分 → 3) LLM抽取结构化标签 → 4) 映射/规范化/路由 → 5) 状态机合并与校验 → 6) 输出结构化病历 + 性能日志
核心入口在 D:\Python\OBFT\PostStruct2.0_14B\code\main.py。
 
1) 输入解析与会话初始化
入口：parse_input_file in D:\Python\OBFT\PostStruct2.0_14B\code\main.py
读取 INPUT_FILE 的内容，用字符串 "end" 切分为多个 session（对话）。
过滤掉无效/过短文本。
生成 session_id 和 text。
会话状态初始化：PostStructureEngine.init_session
通过 MedicalRecordState 创建一个会话级状态（病历状态机）。
初始字段包括 sessionId、dov（就诊日期）、以及各种子模块。
模型定义见 D:\Python\OBFT\PostStruct2.0_14B\code\schemas.py。
 
2) 对话切片（Chunking）
PostStructureEngine.split_into_chunks
默认 lines_per_chunk=4，按行切片，避免医生问话和患者回答被拆散。
每个 chunk 是一个短对话片段。
这是整个流程对 LLM 的“输入窗口”单位。
 
3) 抽取层（LLM Extractor）
实现：LLMExtractor in D:\Python\OBFT\PostStruct2.0_14B\code\llm_extractor.py
读取 prompt 模板：prompt/extract_prompt.txt
构造 LLM messages：system 强制 JSON 数组输出 + user prompt
通过 vLLM 的 OpenAI 兼容接口调用模型（localhost:8000）
解析 JSON：extract_json_array + clean_json_string（清除脏 token/markdown）
输出格式：List[{"key": "...", "value": "...", "raw": "..."}]
可选返回 raw_output 用于记录与调试（return_raw=True）
这是“感知层”：把自然语言对话变成低粒度的结构化标签列表。
 
4) 映射层（路由 + 规范化 + 推断）
实现：route_and_transform in D:\Python\OBFT\PostStruct2.0_14B\code\mapping.py
核心逻辑：
静态映射：SCHEMA_MAP 将 key 映射到结构化字段路径（如 root.age、hpi.lmp）。
动态路由：如果 key 不在静态映射中，则按 CATEGORIES_MAPPING 归入默认 “未分类备注”。
特殊字段处理：
胎心 → 动态构建 fetusExam（多胎索引支持）
数值字段（孕次、产次、年龄等）→ 提取数字转 int
既往史/家族史 → 转换为 StatusDetail(status, details)
日期字段 → normalize_date 对齐 dov 年份
后推理：若未提取到 edd 但有 gwov，用 infer_edd_from_gw 推算预产期
这是“映射层 + 轻推理层”：从标签变成结构化 Patch（可合并更新的差分数据）。
 
5) 状态合并与校验（状态机层）
实现：PostStructureEngine._apply_patch in D:\Python\OBFT\PostStruct2.0_14B\code\main.py
支持 层级模块更新：hpi, pmh, physicalExamination, advice
列表字段 → extend 合并（例如医嘱、服药史）
标量字段 → 直接赋值
根级字段更新（如 gwov, age）
多胎结构：fetusExam 用 dict 索引合并
使用 Pydantic 模型进行类型校验（失败会拦截并打印）
这是“状态机层/风控层”：对 LLM 的提取结果进行结构化合并，确保输出可控且可累积。
 
6) 输出与性能日志
每个 session 输出：session_x.json
调用 MedicalRecordState.to_output_dict()，其中 fetusExam 由 dict 转 list
性能日志：log_performance
包含 LLM 总耗时、端到端耗时、QPS 等

LLM 层独立测试
入口：D:\Python\OBFT\PostStruct2.0_14B\code\llm_layer_test.py
功能：仅测试 LLM 抽取层，记录每个切片的 raw_output、parsed_data、耗时，并将所有结果写入单个 JSON 文件。
输出：output/LLM_Layer_Test_时间戳/llm_test_results.json + performance.log
可选参数：--input, --lines-per-chunk, --output-dir, --dry-run
 
关键数据结构（输出形态）
统一结构定义在 D:\Python\OBFT\PostStruct2.0_14B\code\schemas.py
MedicalRecordState 顶层：sessionId, dov, gwov, age, gravidity, parity, bmi...
子模块：obh, hpi, pmh, fh, physicalExamination, fetusExam, advice
状态字段用 StatusDetail（支持肯定/否认/未提及）
 
工作流关键点与边界行为
切片策略：行级切片避免问答拆开，但对跨行语义仍可能丢失上下文。
日期归一：normalize_date 只支持 MM月DD日 形式，其他格式会原样返回。
孕周推算预产期：只有当模型未给出明确 edd 才会推算，避免覆盖真实值。
多胎处理：胎心 无左右时用动态 index，适用于多胎序列增长。
状态合并：列表字段会累积，适合多轮对话增量抽取。
LLM 输出质量敏感：extract_json_array 依赖 JSON 数组定位，格式偏差会导致空结果。