import re
from collections.abc import Sequence

from agent_platform.domain.memory import (
    RetrievalAcceptanceDecision,
    RetrievalDecision,
    RetrievalHit,
    RetrievalQuery,
)

_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


def _lexical_terms(text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_PATTERN.findall(text)}


class LexicalRetrievalAcceptanceGate:
    def __init__(
        self,
        *,
        min_query_term_coverage: float = 1.0,
    ) -> None:
        if not 0 < min_query_term_coverage <= 1:
            raise ValueError(
                "min_query_term_coverage must be greater than 0 and less than or equal to 1."
            )

        self._min_query_term_coverage = min_query_term_coverage

    async def evaluate(
        self,
        query: RetrievalQuery,
        hits: Sequence[RetrievalHit],
    ) -> RetrievalAcceptanceDecision:
        if not hits:
            return RetrievalAcceptanceDecision(
                decision=RetrievalDecision.ABSTAIN,
                reason_code="no_hits",
                metadata={
                    "hit_count": 0,
                },
            )

        query_terms = _lexical_terms(query.text)

        if not query_terms:
            return RetrievalAcceptanceDecision(
                decision=RetrievalDecision.ABSTAIN,
                reason_code="no_lexical_terms",
                metadata={
                    "hit_count": len(hits),
                },
            )

        if any(hit.memory.scope.namespace != query.scope.namespace for hit in hits):
            return RetrievalAcceptanceDecision(
                decision=RetrievalDecision.ABSTAIN,
                reason_code="scope_mismatch",
                metadata={
                    "hit_count": len(hits),
                },
            )

        top_hit = min(
            hits,
            key=lambda hit: hit.rank,
        )

        memory_terms = _lexical_terms(
            top_hit.memory.content,
        )

        covered_terms = query_terms & memory_terms
        coverage = len(covered_terms) / len(query_terms)

        metadata = {
            "hit_count": len(hits),
            "top_score": top_hit.score,
            "query_term_count": len(query_terms),
            "covered_query_term_count": len(covered_terms),
            "query_term_coverage": coverage,
        }

        if coverage < self._min_query_term_coverage:
            return RetrievalAcceptanceDecision(
                decision=RetrievalDecision.ABSTAIN,
                reason_code="insufficient_query_term_coverage",
                metadata=metadata,
            )

        return RetrievalAcceptanceDecision(
            decision=RetrievalDecision.ACCEPT,
            reason_code="lexical_evidence",
            metadata=metadata,
        )
