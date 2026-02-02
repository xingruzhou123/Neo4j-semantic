"""
RAG Faithfulness Detection.

Verifies whether the LLM-generated answer is fully supported by retrieved evidence.
Uses Natural Language Inference (NLI) approach.
"""

from typing import Tuple, List, Optional


class RAGFaithfulnessCheck:
    """
    RAG Faithfulness Detection using NLI-style prompting.

    Verifies that the generated answer is grounded in the retrieved evidence.
    """

    def __init__(self, llm):
        """
        Initialize the RAG Faithfulness Check.

        Args:
            llm: The LLM instance to use for NLI checking
        """
        self.llm = llm
        print("[DEBUG][RAG-Faithfulness] Initialized")

    def _entailment_check(self, answer: str, evidence: str) -> bool:
        """
        Use LLM to determine if answer is entailed by evidence.

        Args:
            answer: The LLM-generated answer
            evidence: The retrieved evidence/passage

        Returns:
            True if evidence supports the answer, False otherwise
        """
        from langchain_openai import ChatOpenAI
        import config

        # Use temperature=0 for deterministic output
        checker_llm = ChatOpenAI(
            model=config.OPENAI_MODEL,
            api_key=config.OPENAI_API_KEY,
            temperature=0,
            max_tokens=10
        )

        nli_prompt = f"""Evidence:
{evidence}

Answer:
{answer}

Is the Answer fully supported by the Evidence?
Reply with ONLY: YES or NO"""

        response = checker_llm.invoke(nli_prompt)
        result = response.content.strip().upper()

        # Parse response strictly
        return result == "YES" or result.startswith("YES")

    def check(self, answer: str, evidence: Optional[str] = None, evidence_list: Optional[List[str]] = None) -> Tuple[str, str, str]:
        """
        Perform RAG faithfulness check.

        Args:
            answer: The LLM-generated answer
            evidence: Single evidence string (optional)
            evidence_list: List of evidence strings (optional)

        Returns:
            Tuple of (verdict, classification, action)
            - verdict: "YES" or "NO"
            - classification: "Faithful" or "Unfaithful"
            - action: "ALLOW", "WARN", or "BLOCK"
        """
        print(f"\n[DEBUG][RAG-Faithfulness] Starting check...")
        print(f"[DEBUG][RAG-Faithfulness] Answer length: {len(answer)}")

        # Collect all evidence
        all_evidence = []
        if evidence:
            all_evidence.append(evidence)
        if evidence_list:
            all_evidence.extend(evidence_list)

        # If no evidence provided, skip check and allow
        if not all_evidence:
            print("[DEBUG][RAG-Faithfulness] No evidence provided, skipping check")
            print("[DEBUG][RAG-Faithfulness] verdict = N/A")
            print("[DEBUG][RAG-Faithfulness] classification = N/A")
            print("[DEBUG][RAG-Faithfulness] action = ALLOW")
            return ("N/A", "N/A", "ALLOW")

        print(f"[DEBUG][RAG-Faithfulness] Checking against {len(all_evidence)} evidence(s)")

        # Check entailment against each piece of evidence
        entailment_results = []
        for i, evid in enumerate(all_evidence):
            try:
                print(f"[DEBUG][RAG-Faithfulness] Checking evidence {i+1}...")
                is_entailed = self._entailment_check(answer, evid)
                entailment_results.append(is_entailed)
                print(f"[DEBUG][RAG-Faithfulness] Evidence {i+1} entails: {is_entailed}")
            except Exception as e:
                print(f"[DEBUG][RAG-Faithfulness] Error checking evidence {i+1}: {e}")
                entailment_results.append(False)

        # If any evidence supports the answer, consider it faithful
        is_grounded = any(entailment_results)

        if is_grounded:
            verdict = "YES"
            classification = "Faithful"
            action = "ALLOW"
        else:
            verdict = "NO"
            classification = "Unfaithful"
            action = "WARN"  # Use WARN for unfaithful, BLOCK for severe cases

        # Print debug logs (MANDATORY)
        print(f"[DEBUG][RAG-Faithfulness] verdict = {verdict}")
        print(f"[DEBUG][RAG-Faithfulness] classification = {classification}")
        print(f"[DEBUG][RAG-Faithfulness] action = {action}")

        return (verdict, classification, action)
