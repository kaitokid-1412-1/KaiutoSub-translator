"""Tag protection and inline style placeholder preservation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Pattern matching leading ASS override blocks: {\an8}{\pos(10,20)}...
LEAD_OVERRIDE_PATTERN = re.compile(r"^(\{[^{}]*\})+")

# Pattern matching mid-line override blocks or \h
TAG_OR_H_PATTERN = re.compile(r"\{[^{}]*\}|\\h")


@dataclass
class ProtectedLine:
    raw_text: str
    lead: str
    payload: str
    tokens: Dict[str, str] = field(default_factory=dict)
    token_order: List[str] = field(default_factory=list)

    @property
    def has_tokens(self) -> bool:
        return len(self.tokens) > 0


class TagProtector:
    """Protects inline tags (ASS/SRT) during LLM translation."""

    def __init__(self, token_style: str = "bracket"):
        self.token_style = token_style

    def _make_token(self, index: int) -> str:
        # Default token style [[T1]], [[T2]]
        return f"[[T{index}]]"

    def protect(self, raw_text: str) -> ProtectedLine:
        """Extract lead tags and replace inline override tags with safe tokens."""
        if not raw_text:
            return ProtectedLine(raw_text="", lead="", payload="")

        # 1. Keep leading run of override blocks
        lead_match = LEAD_OVERRIDE_PATTERN.match(raw_text)
        if lead_match:
            lead = lead_match.group(0)
            rest = raw_text[len(lead):]
        else:
            lead = ""
            rest = raw_text

        # 2. Replace later override blocks and \h with tokens
        tokens: Dict[str, str] = {}
        token_order: List[str] = []
        counter = 1

        def replace_tag(match: re.Match) -> str:
            nonlocal counter
            tag = match.group(0)
            tok = self._make_token(counter)
            counter += 1
            tokens[tok] = tag
            token_order.append(tok)
            return tok

        tokenized = TAG_OR_H_PATTERN.sub(replace_tag, rest)

        # 3. Convert ASS line breaks \N to real newlines \n in the payload
        payload = tokenized.replace(r"\N", "\n").replace(r"\n", "\n")

        return ProtectedLine(
            raw_text=raw_text,
            lead=lead,
            payload=payload,
            tokens=tokens,
            token_order=token_order,
        )

    def validate_tokens(self, translated_payload: str, protected: ProtectedLine) -> bool:
        """Verify that every expected token is present exactly once in the translation."""
        if not protected.has_tokens:
            return True

        for tok in protected.token_order:
            count = translated_payload.count(tok)
            if count != 1:
                return False
        return True

    def restore(
        self,
        translated_payload: str,
        protected: ProtectedLine,
        is_ass: bool = True,
    ) -> Tuple[str, bool]:
        """Restore tokens and lead override blocks.
        
        Returns (final_text, is_valid).
        """
        valid = self.validate_tokens(translated_payload, protected)

        if not valid:
            # Degraded restore: remove tokens and restore lead
            restored = self.degraded_restore(translated_payload, protected, is_ass=is_ass)
            return restored, False

        text = translated_payload
        for tok in protected.token_order:
            text = text.replace(tok, protected.tokens[tok])

        # Convert real newlines back to \N if ASS
        if is_ass:
            text = text.replace("\r\n", "\n").replace("\n", r"\N")

        final_text = protected.lead + text
        return final_text, True

    def degraded_restore(
        self,
        translated_payload: str,
        protected: ProtectedLine,
        is_ass: bool = True,
    ) -> str:
        """Strip any broken/leftover tokens and restore only lead tags."""
        text = translated_payload
        # Strip all known tokens or token-like artifacts [[T...]]
        for tok in protected.tokens.keys():
            text = text.replace(tok, "")
        text = re.sub(r"\[\[T\d+\]\]", "", text)

        if is_ass:
            text = text.replace("\r\n", "\n").replace("\n", r"\N")

        return protected.lead + text

