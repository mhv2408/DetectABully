"""
AI-powered toxicity detection using Perspective API and OpenAI
"""

import re
import aiohttp
from typing import Dict, Tuple
from googleapiclient import discovery
from config.settings import PERSPECTIVE_API_KEY, OPENAI_API_KEY, FALLBACK_PATTERNS

class ToxicityDetector:
    """Handles AI-based toxicity detection with fallback patterns"""
    
    def __init__(self):
        self.perspective_service = None
        self.fallback_patterns = self._compile_fallback_patterns()
        
    def _compile_fallback_patterns(self) -> Dict:
        """Compile regex patterns for fallback detection"""
        return {
            level: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            for level, patterns in FALLBACK_PATTERNS.items()
        }
    
    async def check_perspective_api(self, text: str) -> Tuple[float, Dict]:
        """
        Check toxicity using Google Perspective API
        
        Returns:
            Tuple[float, Dict]: (max_score, all_scores)
        """
        if not PERSPECTIVE_API_KEY:
            return 0.0, {}
        
        try:
            if not self.perspective_service:
                self.perspective_service = discovery.build(
                    'commentanalyzer', 'v1alpha1',
                    developerKey=PERSPECTIVE_API_KEY,
                    discoveryServiceUrl="https://commentanalyzer.googleapis.com/$discovery/rest?version=v1alpha1"
                )
            
            analyze_request = {
                'comment': {'text': text},
                'languages':["en"],
                'requestedAttributes': {
                    'TOXICITY': {},
                    'SEVERE_TOXICITY': {},
                    'IDENTITY_ATTACK': {},
                    'INSULT': {},
                    'PROFANITY': {},
                    'THREAT': {},
                    'SEXUALLY_EXPLICIT': {},
                    'FLIRTATION': {}
                }
            }
            
            response = self.perspective_service.comments().analyze(body=analyze_request).execute()
            
            scores = {}
            for attribute, data in response['attributeScores'].items():
                scores[attribute] = data['summaryScore']['value']
            
            # Get the highest toxicity score
            max_score = max(scores.values()) if scores else 0.0
            return max_score, scores
            
        except Exception as e:
            print(f"Perspective API error: {e}")
            return 0.0, {}
    
    async def check_openai_moderation(self, text: str) -> Tuple[bool, Dict, float]:
        """
        Check content using OpenAI Moderation API
        
        Returns:
            Tuple[bool, Dict, float]: (flagged, categories, confidence)
        """
        if not OPENAI_API_KEY:
            return False, {}, 0.0
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'Authorization': f'Bearer {OPENAI_API_KEY}',
                    'Content-Type': 'application/json'
                }
                data = {'input': text}
                
                async with session.post(
                    'https://api.openai.com/v1/moderations',
                    headers=headers, 
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        moderation = result['results'][0]
                        
                        # Calculate confidence based on category scores
                        category_scores = moderation.get('category_scores', {})
                        max_confidence = max(category_scores.values()) if category_scores else 0.0
                        
                        return moderation['flagged'], moderation['categories'], max_confidence
                    return False, {}, 0.0
                    
        except Exception as e:
            print(f"OpenAI Moderation error: {e}")
            return False, {}, 0.0
    
    def check_fallback_patterns(self, text: str) -> Tuple[str, str]:
        """
        Fallback pattern matching when APIs fail
        
        Returns:
            Tuple[str, str]: (severity_level, reason)
        """
        for level, patterns in self.fallback_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    return level, f"pattern match ({level})"
        return "none", ""
    
    async def analyze_toxicity(self, text: str) -> Dict:
        """
        Comprehensive toxicity analysis using multiple methods
        
        Returns:
            Dict: Complete analysis results
        """
        # Run both AI detections concurrently
        perspective_task = self.check_perspective_api(text)
        openai_task = self.check_openai_moderation(text)
        
        perspective_score, perspective_details = await perspective_task
        openai_flagged, openai_categories, openai_confidence = await openai_task
        
        # Fallback detection
        fallback_level, fallback_reason = self.check_fallback_patterns(text)
        
        return {
            "perspective": {
                "score": perspective_score,
                "details": perspective_details
            },
            "openai": {
                "flagged": openai_flagged,
                "categories": openai_categories,
                "confidence": openai_confidence
            },
            "fallback": {
                "level": fallback_level,
                "reason": fallback_reason
            },
            "text_length": len(text),
            "word_count": len(text.split())
        }