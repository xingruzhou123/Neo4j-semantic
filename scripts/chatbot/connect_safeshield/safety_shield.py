"""
Safety Shield - Combined Safety Decision Logic.

Executes both Self-Consistency and RAG Faithfulness checks,
and determines the final safety action.
"""

from typing import Tuple, Optional, List, Dict, Any
from .self_consistency import SelfConsistencyCheck
from .rag_faithfulness import RAGFaithfulnessCheck


class SafetyShield:
    """
    Combined Safety Shield that runs both hallucination detection
    and RAG faithfulness checks.
    """

    def __init__(self, llm, enable_self_consistency: bool = True, enable_rag_faithfulness: bool = True):
        """
        Initialize the Safety Shield.

        Args:
            llm: The LLM instance to use for checks
            enable_self_consistency: Whether to enable self-consistency check
            enable_rag_faithfulness: Whether to enable RAG faithfulness check
        """
        self.llm = llm
        self.enable_self_consistency = enable_self_consistency
        self.enable_rag_faithfulness = enable_rag_faithfulness

        print("\n" + "="*60)
        print("[SafetyShield] Initializing Safety Shield...")

        if enable_self_consistency:
            self.self_consistency_check = SelfConsistencyCheck(llm)
            print("[SafetyShield] Self-Consistency Check: ENABLED")
        else:
            self.self_consistency_check = None
            print("[SafetyShield] Self-Consistency Check: DISABLED")

        if enable_rag_faithfulness:
            self.rag_faithfulness_check = RAGFaithfulnessCheck(llm)
            print("[SafetyShield] RAG Faithfulness Check: ENABLED")
        else:
            self.rag_faithfulness_check = None
            print("[SafetyShield] RAG Faithfulness Check: DISABLED")

        print("[SafetyShield] Initialization complete")
        print("="*60 + "\n")

    def _determine_final_action(self, actions: List[str]) -> str:
        """
        Determine final action based on most restrictive outcome.

        Priority: BLOCK > WARN > ALLOW

        Args:
            actions: List of action strings from individual checks

        Returns:
            Final action: "BLOCK", "WARN", or "ALLOW"
        """
        if "BLOCK" in actions:
            return "BLOCK"
        elif "WARN" in actions:
            return "WARN"
        else:
            return "ALLOW"

    def check(
        self,
        answer: str,
        question: str,
        evidence: Optional[str] = None,
        evidence_list: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Run all enabled safety checks and return combined result.

        Args:
            answer: The LLM-generated answer
            question: The original user question
            evidence: Single evidence string for RAG check (optional)
            evidence_list: List of evidence strings for RAG check (optional)
            context: Additional context dictionary (optional)

        Returns:
            Tuple of (final_action, modified_answer, details)
            - final_action: "BLOCK", "WARN", or "ALLOW"
            - modified_answer: The answer (possibly modified based on action)
            - details: Dictionary with detailed results from each check
        """
        print("\n" + "="*60)
        print("[SafetyShield] Running Safety Checks...")
        print("="*60)

        actions = []
        details = {
            "self_consistency": None,
            "rag_faithfulness": None,
        }

        # Run Self-Consistency Check
        if self.enable_self_consistency and self.self_consistency_check:
            print("\n[SafetyShield] >>> Running Self-Consistency Check")
            sc_verdict, sc_avg_sim, sc_action = self.self_consistency_check.check(answer, question)
            actions.append(sc_action)
            details["self_consistency"] = {
                "verdict": sc_verdict,
                "avg_sim": sc_avg_sim,
                "action": sc_action
            }

        # Run RAG Faithfulness Check
        if self.enable_rag_faithfulness and self.rag_faithfulness_check:
            print("\n[SafetyShield] >>> Running RAG Faithfulness Check")

            # Extract evidence from context if provided
            if context and "retrieved_docs" in context:
                evidence_list = context.get("retrieved_docs", [])

            # Also check for cypher query results as evidence
            if context and "cypher_results" in context:
                cypher_evidence = str(context.get("cypher_results", ""))
                if cypher_evidence:
                    if evidence_list is None:
                        evidence_list = []
                    evidence_list.append(cypher_evidence)

            rf_verdict, rf_classification, rf_action = self.rag_faithfulness_check.check(
                answer, evidence, evidence_list
            )
            actions.append(rf_action)
            details["rag_faithfulness"] = {
                "verdict": rf_verdict,
                "classification": rf_classification,
                "action": rf_action
            }

        # Determine final action (most restrictive)
        final_action = self._determine_final_action(actions)

        # Modify answer based on final action
        if final_action == "BLOCK":
            modified_answer = (
                "I apologize, but I cannot provide a reliable answer to your question. "
                "The response failed safety checks and may contain inaccurate information. "
                "Please try rephrasing your question or consult authoritative sources."
            )
        elif final_action == "WARN":
            modified_answer = (
                f"**[Warning: This response may contain inaccuracies. Please verify the information.]**\n\n"
                f"{answer}"
            )
        else:
            modified_answer = answer

        # Print final decision
        print("\n" + "-"*60)
        print(f"[SafetyShield] FINAL DECISION: {final_action}")
        print(f"[SafetyShield] Individual actions: {actions}")
        print("-"*60 + "\n")

        return (final_action, modified_answer, details)


def apply_safety_shield(
    answer: str,
    question: str,
    llm,
    evidence: Optional[str] = None,
    evidence_list: Optional[List[str]] = None,
    context: Optional[Dict[str, Any]] = None,
    enable_self_consistency: bool = True,
    enable_rag_faithfulness: bool = True
) -> str:
    """
    Convenience function to apply safety shield to an answer.

    Args:
        answer: The LLM-generated answer
        question: The original user question
        llm: The LLM instance
        evidence: Single evidence string (optional)
        evidence_list: List of evidence strings (optional)
        context: Additional context (optional)
        enable_self_consistency: Enable self-consistency check
        enable_rag_faithfulness: Enable RAG faithfulness check

    Returns:
        Modified answer after safety checks
    """
    shield = SafetyShield(
        llm,
        enable_self_consistency=enable_self_consistency,
        enable_rag_faithfulness=enable_rag_faithfulness
    )

    final_action, modified_answer, details = shield.check(
        answer=answer,
        question=question,
        evidence=evidence,
        evidence_list=evidence_list,
        context=context
    )

    return modified_answer
