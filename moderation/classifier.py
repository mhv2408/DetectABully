"""
Message classification logic for determining moderation actions
Enhanced with Community Immunity System
"""

import re
from typing import Tuple, Set
from moderation.detector import ToxicityDetector
from config.settings import TOXICITY_THRESHOLDS
from data.whitelist_repo import wl_is_whitelisted
from data.strikes_repo import get_user_immunity, process_clean_message

class MessageClassifier:
    """Handles message analysis and classification with immunity system"""
    
    def __init__(self):
        self.detector = ToxicityDetector()
        
        # Compile regex patterns for rule-based checks
        self.spam_patterns = [
            re.compile(r"(.)\1{4,}", re.IGNORECASE),  # repeated characters
            re.compile(r"(.+?)\1{3,}", re.IGNORECASE),  # repeated phrases
            re.compile(r"[!@#$%^&*]{5,}", re.IGNORECASE),  # excessive punctuation
        ]
        
        self.invite_pattern = re.compile(
            r"discord\.gg/[a-zA-Z0-9]+|discordapp\.com/invite/[a-zA-Z0-9]+", 
            re.IGNORECASE
        )
        
        self.suspicious_links = re.compile(
            r"(bit\.ly|tinyurl|t\.co|goo\.gl)/\S+", 
            re.IGNORECASE
        )
    
    def is_caps_spam(self, text: str) -> bool:
        """Detect excessive caps usage"""
        letters = [c for c in text if c.isalpha()]
        if len(letters) < 8:
            return False
        
        caps = sum(1 for c in letters if c.isupper())
        caps_ratio = caps / len(letters)
        
        # More lenient for shorter messages
        threshold = 0.8 if len(letters) < 20 else 0.7
        return caps_ratio > threshold
    
    def is_spam(self, text: str) -> bool:
        """Detect various spam patterns"""
        return any(pattern.search(text) for pattern in self.spam_patterns)
    
    def is_targeted_harassment(self, text: str) -> bool:
        """Detect targeted harassment with mentions"""
        has_mention = any(mention in text for mention in ["<@", "@everyone", "@here"])
        if not has_mention:
            return False
        
        # Check for aggressive patterns with mentions
        aggressive_patterns = [
            r"(shut up|stfu|go away|leave|nobody wants)",
            r"(hate|despise|can't stand).*you",
            r"you.*(suck|terrible|awful|worst)"
        ]
        
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in aggressive_patterns)
    
    def has_suspicious_content(self, text: str) -> Tuple[bool, str]:
        """Detect suspicious links or invites"""
        if self.invite_pattern.search(text):
            return True, "unauthorized invite"
        if self.suspicious_links.search(text):
            return True, "suspicious link"
        return False, ""
    
    async def classify_message(self, text: str, author_id: int, guild_id: str) -> Tuple[str, str, dict]:
        """
        Enhanced classification with immunity system
        
        Returns:
            Tuple[str, str, dict]: (severity_level, reason, analysis_data)
        """
        text = text.strip()
        if not text:
            return "none", "empty message", {}
        
        # Check database whitelist first
        if await wl_is_whitelisted(str(guild_id), str(author_id)):
            return "none", "database whitelisted user", {}
        
        # Get user's immunity status
        immunity = await get_user_immunity(str(guild_id), str(author_id))
        
        # Get AI analysis
        analysis = await self.detector.analyze_toxicity(text)
        perspective_score = analysis["perspective"]["score"]
        openai_flagged = analysis["openai"]["flagged"]
        openai_categories = analysis["openai"]["categories"]
        openai_confidence = analysis["openai"]["confidence"]
        
        # Add immunity info to analysis
        analysis["immunity"] = immunity
        
        # Process clean messages for positive points
        if perspective_score < 0.2 and not openai_flagged:
            await process_clean_message(str(guild_id), str(author_id), text, perspective_score)
            # Still continue with analysis in case of rule violations
        
        # Determine base severity from AI
        base_severity = self._get_base_severity(perspective_score, openai_flagged, openai_categories, openai_confidence)
        
        # Apply immunity filtering
        final_severity, immunity_reason = self._apply_immunity_filter(base_severity, perspective_score, immunity)
        
        if final_severity != "none":
            # Check rule-based violations (these bypass some immunity)
            rule_violation = self._check_rule_violations(text)
            if rule_violation[0] != "none":
                # Rule violations have different immunity rules
                final_severity, immunity_reason = self._apply_immunity_to_rules(rule_violation, immunity)
                if final_severity != "none":
                    return final_severity, rule_violation[1], analysis
        
        # Return AI-based result with immunity applied
        if final_severity == "none" and immunity_reason:
            return "none", f"immune: {immunity_reason}", analysis
        elif final_severity != "none":
            ai_reason = f"AI detected: {base_severity} toxicity ({perspective_score:.2f})"
            return final_severity, ai_reason, analysis
        
        return "none", "clean message", analysis
    
    def _get_base_severity(self, perspective_score: float, openai_flagged: bool, 
                          openai_categories: dict, openai_confidence: float) -> str:
        """Get base severity before immunity filtering"""
        
        # Check for severe violations first
        if (perspective_score >= TOXICITY_THRESHOLDS["severe"] or 
            (openai_flagged and self._is_severe_openai_violation(openai_categories))):
            return "severe"
        
        # Check moderate violations
        elif (perspective_score >= TOXICITY_THRESHOLDS["moderate"] or 
              (openai_flagged and openai_confidence > 0.7)):
            return "flag"
        
        # Check mild violations
        elif perspective_score >= TOXICITY_THRESHOLDS["mild"]:
            return "warn"
        
        return "none"
    
    def _apply_immunity_filter(self, base_severity: str, perspective_score: float, 
                             immunity: dict) -> Tuple[str, str]:
        """Apply immunity filtering to base severity"""
        
        if base_severity == "none":
            return "none", ""
        
        immunity_level = immunity["immunity_level"]
        
        # Severe violations bypass most immunity (guardian level can still get them)
        if base_severity == "severe":
            if immunity_level == "guardian" and perspective_score < 0.85:
                return "none", f"guardian immunity (score: {perspective_score:.2f})"
            return base_severity, ""
        
        # Moderate violations (flags)
        elif base_severity == "flag":
            if immunity["can_bypass_minor_flags"]:
                return "none", f"{immunity_level} immunity bypassed minor flag"
            return base_severity, ""
        
        # Mild violations (warnings)  
        elif base_severity == "warn":
            if immunity["can_bypass_warnings"]:
                return "none", f"{immunity_level} immunity bypassed warning"
            return base_severity, ""
        
        return base_severity, ""
    
    def _check_rule_violations(self, text: str) -> Tuple[str, str]:
        """Check for rule-based violations"""
        
        if self.is_targeted_harassment(text):
            return "flag", "targeted harassment"
        
        is_suspicious, sus_reason = self.has_suspicious_content(text)
        if is_suspicious:
            return "flag", sus_reason
        
        if self.is_spam(text):
            return "warn", "spam detected"
        
        if self.is_caps_spam(text):
            return "warn", "excessive caps"
        
        return "none", ""
    
    def _apply_immunity_to_rules(self, rule_violation: Tuple[str, str], 
                               immunity: dict) -> Tuple[str, str]:
        """Apply immunity to rule-based violations (more restrictive)"""
        
        severity, reason = rule_violation
        immunity_level = immunity["immunity_level"]
        
        # Rule violations are harder to bypass
        if severity == "flag":
            # Only guardian level can bypass rule-based flags
            if immunity_level == "guardian":
                return "none", f"guardian immunity bypassed {reason}"
            return severity, ""
        
        elif severity == "warn":
            # Veteran+ can bypass rule-based warnings
            if immunity["can_bypass_minor_flags"]:  # veteran or guardian
                return "none", f"{immunity_level} immunity bypassed {reason}"
            return severity, ""
        
        return severity, ""
    
    def _is_severe_openai_violation(self, categories: dict) -> bool:
        """Check if OpenAI categories indicate severe violation"""
        severe_categories = [
            'hate', 'hate/threatening', 'violence', 'violence/graphic',
            'harassment', 'harassment/threatening', 'self-harm'
        ]
        return any(categories.get(cat, False) for cat in severe_categories)