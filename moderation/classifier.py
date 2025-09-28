"""
Message classification logic for determining moderation actions
"""

import re
from typing import Tuple, Set
from moderation.detector import ToxicityDetector
from config.settings import TOXICITY_THRESHOLDS

class MessageClassifier:
    """Handles message analysis and classification"""
    
    def __init__(self):
        self.detector = ToxicityDetector()
        self.whitelist: Set[int] = set()
        
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
    
    def add_to_whitelist(self, user_id: int):
        """Add user to moderation whitelist"""
        self.whitelist.add(user_id)
    
    def remove_from_whitelist(self, user_id: int):
        """Remove user from moderation whitelist"""
        self.whitelist.discard(user_id)
    
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
    
    async def classify_message(self, text: str, author_id: int) -> Tuple[str, str, dict]:
        """
        Classify message for moderation action
        
        Returns:
            Tuple[str, str, dict]: (severity_level, reason, analysis_data)
        """
        # Skip whitelisted users
        if author_id in self.whitelist:
            return "none", "whitelisted user", {}
        
        text = text.strip()
        if not text:
            return "none", "empty message", {}
        
        # Get AI analysis
        analysis = await self.detector.analyze_toxicity(text)
        
        # Determine severity based on AI results
        perspective_score = analysis["perspective"]["score"]
        openai_flagged = analysis["openai"]["flagged"]
        openai_categories = analysis["openai"]["categories"]
        openai_confidence = analysis["openai"]["confidence"]
        
        # AI-based classification
        if (perspective_score >= TOXICITY_THRESHOLDS["severe"] or 
            (openai_flagged and self._is_severe_openai_violation(openai_categories))):
            return "severe", f"AI detected: high toxicity ({perspective_score:.2f})", analysis
        
        elif (perspective_score >= TOXICITY_THRESHOLDS["moderate"] or 
              (openai_flagged and openai_confidence > 0.7)):
            return "flag", f"AI detected: moderate toxicity ({perspective_score:.2f})", analysis
        
        elif perspective_score >= TOXICITY_THRESHOLDS["mild"]:
            return "warn", f"AI detected: mild toxicity ({perspective_score:.2f})", analysis
        
        # Fallback to pattern matching if AI confidence is low
        if perspective_score == 0.0 and not openai_flagged:
            fallback_level = analysis["fallback"]["level"]
            fallback_reason = analysis["fallback"]["reason"]
            if fallback_level != "none":
                return fallback_level, f"fallback {fallback_reason}", analysis
        
        # Rule-based checks
        if self.is_targeted_harassment(text):
            return "flag", "targeted harassment", analysis
        
        is_suspicious, sus_reason = self.has_suspicious_content(text)
        if is_suspicious:
            return "flag", sus_reason, analysis
        
        if self.is_spam(text):
            return "warn", "spam detected", analysis
        
        if self.is_caps_spam(text):
            return "warn", "excessive caps", analysis
        
        return "none", "clean message", analysis
    
    def _is_severe_openai_violation(self, categories: dict) -> bool:
        """Check if OpenAI categories indicate severe violation"""
        severe_categories = [
            'hate', 'hate/threatening', 'violence', 'violence/graphic',
            'harassment', 'harassment/threatening', 'self-harm'
        ]
        return any(categories.get(cat, False) for cat in severe_categories)