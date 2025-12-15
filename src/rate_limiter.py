"""
Rate limiting for MCP tool calls.

Protects system from spam requests and helps future agents by preventing
resource exhaustion and ensuring fair access.
"""

from typing import Dict, Optional
from collections import defaultdict, deque
import time


class RateLimiter:
    """
    Simple token bucket rate limiter per agent.
    
    Prevents agents from overwhelming the system with rapid requests.
    """
    
    def __init__(self, max_requests_per_minute: int = 60, 
                 max_requests_per_hour: int = 1000):
        """
        Initialize rate limiter.
        
        Args:
            max_requests_per_minute: Max requests per minute per agent (default: 60)
            max_requests_per_hour: Max requests per hour per agent (default: 1000)
        """
        self.max_per_minute = max_requests_per_minute
        self.max_per_hour = max_requests_per_hour
        
        # Per-agent request queues
        # Format: {agent_id: deque of timestamps}
        self.request_history: Dict[str, deque] = defaultdict(lambda: deque())
    
    def _cleanup_old_requests(self, agent_id: str, window_seconds: int) -> None:
        """Remove requests older than window from history"""
        now = time.time()
        cutoff = now - window_seconds
        
        history = self.request_history[agent_id]
        while history and history[0] < cutoff:
            history.popleft()
    
    def check_rate_limit(self, agent_id: str) -> tuple[bool, Optional[str]]:
        """
        Check if agent has exceeded rate limits.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            (allowed, error_message)
            - allowed: True if request allowed, False if rate limited
            - error_message: None if allowed, error message if rate limited
        """
        now = time.time()
        history = self.request_history[agent_id]
        
        # Clean up old requests (keep last hour)
        self._cleanup_old_requests(agent_id, window_seconds=3600)
        
        # Check per-minute limit
        minute_cutoff = now - 60
        recent_minute = sum(1 for ts in history if ts > minute_cutoff)
        
        if recent_minute >= self.max_per_minute:
            return False, f"Rate limit exceeded: {recent_minute}/{self.max_per_minute} requests per minute. Wait a few seconds and retry."
        
        # Check per-hour limit
        hour_cutoff = now - 3600
        recent_hour = sum(1 for ts in history if ts > hour_cutoff)
        
        if recent_hour >= self.max_per_hour:
            return False, f"Rate limit exceeded: {recent_hour}/{self.max_per_hour} requests per hour. Please reduce request frequency."
        
        # Record this request
        history.append(now)
        
        return True, None
    
    def get_stats(self, agent_id: str) -> Dict[str, int]:
        """Get rate limit statistics for an agent"""
        now = time.time()
        history = self.request_history[agent_id]
        
        # Clean up old requests
        self._cleanup_old_requests(agent_id, window_seconds=3600)
        
        minute_cutoff = now - 60
        hour_cutoff = now - 3600
        
        requests_last_minute = sum(1 for ts in history if ts > minute_cutoff)
        requests_last_hour = sum(1 for ts in history if ts > hour_cutoff)
        
        return {
            'requests_last_minute': requests_last_minute,
            'requests_last_hour': requests_last_hour,
            'limit_per_minute': self.max_per_minute,
            'limit_per_hour': self.max_per_hour,
            'remaining_minute': max(0, self.max_per_minute - requests_last_minute),
            'remaining_hour': max(0, self.max_per_hour - requests_last_hour)
        }
    
    def reset(self, agent_id: Optional[str] = None) -> None:
        """
        Reset rate limit history.
        
        Args:
            agent_id: If provided, reset only this agent. Otherwise reset all.
        """
        if agent_id:
            self.request_history[agent_id].clear()
        else:
            self.request_history.clear()


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(max_requests_per_minute=60, max_requests_per_hour=1000)
    return _rate_limiter

