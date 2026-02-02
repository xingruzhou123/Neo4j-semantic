class RAGFaithfulnessRule(BaseOutputRule):
    """
    使用 LLM-based Entailment Check 验证答案是否基于检索证据
    """

    def __init__(
        self,
        name="rag_faithfulness_check",
        shared_llm=None,
        **kwargs,
    ):
        self.llm_checker = shared_llm or VLLMOpenAIClient(
            base_url="http://localhost:8000/v1",
            model_name="Qwen/Qwen3-4B-Instruct-2507",
        )

    async def _entailment_check(self, answer: str, evidence: str) -> bool:
        """
        使用 LLM 判断 answer 是否可以从 evidence 推断出来
        """
        prompt = [
            {
                "role": "system",
                "content": "You are a meticulous fact-checker. Your task is to "
                           "determine if the 'hypothesis' is entirely grounded in "
                           "and entailed by the provided 'evidence'. "
                           "Respond only with the word 'YES' or 'NO'.",
            },
            {
                "role": "user",
                "content": f"Evidence: {evidence}\n"
                           f"Hypothesis: {answer}\n"
                           f"Does the evidence entail the hypothesis? (YES/NO)",
            },
        ]

        response = await self.llm_checker.acomplete(
            messages=prompt, 
            temperature=0.001,  # 接近确定性输出
            max_tokens=5
        )
        return response.strip().upper() == "YES"

    async def apply(self, text: str, context: dict) -> OutputRuleResult:
        """
        验证 LLM 生成的回答是否基于检索到的证据
        """
        evidence_list = context.get("retrieved_docs", [])
        if not evidence_list:
            return OutputRuleResult(action="allow", text=text)

        answer = text

        # 对每个证据并行检查
        check_tasks = [
            self._entailment_check(answer, evid) 
            for evid in evidence_list
        ]
        entailment_results = await asyncio.gather(*check_tasks)

        # 只要有一个证据支持，就认为是忠实的
        is_grounded = any(entailment_results)

        if is_grounded:
            print("[RAGFaithfulnessRule] ✅ Grounded")
            return OutputRuleResult(action="allow", text=text)
        else:
            print("[RAGFaithfulnessRule] 🛑 Not Grounded")
            return OutputRuleResult(
                action="warn", 
                text=text, 
                reason="Answer not grounded in evidence"
            )