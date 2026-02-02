class SelfConsistencyRule(BaseOutputRule):
    """
    自我验证规则：
    1. 接收一个答案
    2. 生成 N 个对该答案的"事实核查"回复
    3. 比较原始答案和事实核查回复之间的语义相似度
    4. 低相似度 → 可能是幻觉或自相矛盾
    """

    def __init__(
        self,
        name: str,
        shared_llm: BaseLLM, 
        num_alternates: int = 2,        # 生成几个验证回答
        mode: str = "warn",
        block_threshold: float = 0.5,   # 低于此值 → 拦截
        warn_threshold: float = 0.75,   # 低于此值 → 警告
    ):
        self.encoder = SentenceTransformer("all-MiniLM-L6-v2")
        ...

    async def _get_verification(self, text_to_check: str) -> str:
        """用 LLM 生成一个验证（事实核查）"""
        prompt = [
            {
                "role": "system",
                "content": "You are a meticulous fact-checker. Evaluate the following "
                           "statement for factual accuracy. If it is accurate, repeat "
                           "the statement. If it is inaccurate, provide the correction.",
            },
            {"role": "user", "content": text_to_check},
        ]
        return await self.verification_llm.acomplete(prompt, temperature=0.5)

    async def apply(self, text: str, context: dict) -> OutputRuleResult:
        # 1. 生成 N 个验证回答
        verification_tasks = [
            self._get_verification(text) for _ in range(self.num_alternates)
        ]
        verifications = await asyncio.gather(*verification_tasks)

        # 2. 编码所有文本
        all_texts = [text] + [v for v in verifications if v]
        embeddings = self.encoder.encode(all_texts, convert_to_tensor=True)

        # 3. 计算语义相似度
        similarities = util.cos_sim(embeddings[0], embeddings[1:]).flatten()
        avg_similarity = np.mean([s.item() for s in similarities])

        # 4. 根据阈值判断
        if avg_similarity < self.block_threshold:
            return OutputRuleResult(action="block", reason="高概率幻觉")
        
        if avg_similarity < self.warn_threshold:
            return OutputRuleResult(action="warn", reason="可能幻觉")
        
        return OutputRuleResult(action="allow")


### 示例运行日志
# ```
# [SelfConsistencyRule] 🚀 called with text[:50]='Finland has not banned Ozempic. In fact, Ozempic ('
# [SelfConsistencyRule] 🔧 has encoder: True, verification_llm: True
# [SelfConsistencyRule] 🧩 verification outputs = [
#     'Finland has not banned Ozempic. In fact, Ozempic (semaglutide) is a prescription...',
#     'The statement is accurate. Finland has not banned Ozempic...'
# ]
# [SelfConsistencyRule] Avg. Similarity: 0.918 (Block < 0.5, Warn < 0.75)