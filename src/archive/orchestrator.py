"""
UNITARES Orchestrator - Composable Workflows

Instead of 43 tools called individually, this provides
high-level workflows that compose them meaningfully.

Design Principles:
1. Log on thermodynamic significance, not routine
2. Export flows OUT, not just metrics IN
3. Single entry points for common operations
4. Self-cleaning: entropy out, not just in

Version: 0.1.0
Date: 2025-11-29
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from pathlib import Path
import json


class Orchestrator:
    """
    High-level workflows for governance operations.
    
    Composes existing tools into meaningful operations
    rather than requiring manual tool-by-tool composition.
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path(__file__).parent.parent / "data"
        self.exports_dir = self.data_dir / "exports"
        self.exports_dir.mkdir(exist_ok=True)
        
        # Thresholds for "thermodynamic significance"
        self.significance_thresholds = {
            'risk_spike': 0.15,        # Risk increase > 15% is significant
            'coherence_drop': 0.10,    # Coherence drop > 10% is significant  
            'void_threshold': 0.10,    # |V| > 0.10 is significant
            'entropy_spike': 0.20,     # S increase > 20% is significant
        }
    
    # ─────────────────────────────────────────────────────────────
    # WORKFLOW 1: Governance Cycle with Automatic Export
    # ─────────────────────────────────────────────────────────────
    
    def governance_cycle(
        self,
        agent_id: str,
        api_key: str,
        complexity: float = 0.5,
        response_text: str = "",
        auto_export: bool = True,
    ) -> Dict[str, Any]:
        """
        Run governance cycle and export if thermodynamically significant.
        
        This replaces the pattern of:
            1. process_agent_update()
            2. manually check if significant
            3. maybe export_to_file()
            4. maybe store_knowledge_graph()
        
        Returns:
            Combined result with decision, metrics, and export status
        """
        from src.governance_monitor import GovernanceMonitor
        
        # Get or create monitor
        monitor = GovernanceMonitor.get_or_create(agent_id)
        
        # Run the update
        result = monitor.process_update(
            complexity=complexity,
            response_text=response_text,
        )
        
        # Check thermodynamic significance
        significance = self._assess_significance(monitor, result)
        
        # Auto-export if significant
        export_result = None
        if auto_export and significance['is_significant']:
            export_result = self._export_significant_event(
                agent_id=agent_id,
                result=result,
                significance=significance,
            )
        
        return {
            'decision': result.get('decision'),
            'metrics': result.get('metrics'),
            'significance': significance,
            'exported': export_result is not None,
            'export_path': export_result.get('file_path') if export_result else None,
        }
    
    def _assess_significance(
        self, 
        monitor, 
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Determine if this update is thermodynamically significant.
        
        Significant events worth logging:
        - Risk spiked
        - Coherence dropped significantly  
        - Void crossed threshold
        - Circuit breaker triggered
        - Decision changed from proceed to pause
        """
        metrics = result.get('metrics', {})
        state = monitor.state
        
        reasons = []
        
        # Check risk spike
        if len(state.risk_history) >= 2:
            risk_delta = metrics.get('risk_score', 0) - state.risk_history[-2]
            if risk_delta > self.significance_thresholds['risk_spike']:
                reasons.append(f"risk_spike: +{risk_delta:.3f}")
        
        # Check coherence drop
        if len(state.coherence_history) >= 2:
            coh_delta = state.coherence_history[-2] - metrics.get('coherence', 1)
            if coh_delta > self.significance_thresholds['coherence_drop']:
                reasons.append(f"coherence_drop: -{coh_delta:.3f}")
        
        # Check void threshold
        V = metrics.get('V', 0)
        if abs(V) > self.significance_thresholds['void_threshold']:
            reasons.append(f"void_significant: V={V:.3f}")
        
        # Check circuit breaker
        if result.get('circuit_breaker', {}).get('triggered'):
            reasons.append("circuit_breaker_triggered")
        
        # Check decision type
        decision = result.get('decision', {}).get('action', '')
        if decision in ['pause', 'reject']:
            reasons.append(f"decision: {decision}")
        
        return {
            'is_significant': len(reasons) > 0,
            'reasons': reasons,
            'timestamp': datetime.now().isoformat(),
        }
    
    def _export_significant_event(
        self,
        agent_id: str,
        result: Dict[str, Any],
        significance: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Export a significant event to the exports directory."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{agent_id}_significant_{timestamp}.json"
        filepath = self.exports_dir / filename
        
        export_data = {
            'agent_id': agent_id,
            'timestamp': significance['timestamp'],
            'significance_reasons': significance['reasons'],
            'decision': result.get('decision'),
            'metrics': result.get('metrics'),
        }
        
        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        return {
            'file_path': str(filepath),
            'filename': filename,
        }

    # ─────────────────────────────────────────────────────────────
    # WORKFLOW 2: Daily Maintenance (Self-Cleaning)
    # ─────────────────────────────────────────────────────────────
    
    def daily_maintenance(
        self,
        archive_days: int = 7,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Run daily maintenance to prevent entropy accumulation.
        
        Operations:
        1. Archive stale agents (inactive > archive_days)
        2. Clean orphan lock files
        3. Generate fleet health summary
        4. Export summary artifact
        
        This replaces manual calls to:
            - archive_old_test_agents()
            - cleanup_stale_locks()
            - aggregate_metrics()
            - export_to_file() for each
        """
        results = {
            'timestamp': datetime.now().isoformat(),
            'dry_run': dry_run,
            'archived_agents': [],
            'cleaned_locks': 0,
            'fleet_health': {},
            'export_path': None,
        }
        
        # 1. Archive stale agents
        from src.agent_id_manager import AgentIdManager
        manager = AgentIdManager()
        
        cutoff = datetime.now() - timedelta(days=archive_days)
        stale_agents = []
        
        for agent_id in manager.list_agents():
            metadata = manager.get_agent_metadata(agent_id)
            last_update = metadata.get('last_update')
            if last_update:
                last_dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                if last_dt.replace(tzinfo=None) < cutoff:
                    # Only archive test/demo agents, not production
                    if any(x in agent_id.lower() for x in ['test', 'demo', 'tmp']):
                        stale_agents.append(agent_id)
        
        if not dry_run:
            for agent_id in stale_agents:
                manager.archive_agent(agent_id, reason=f"Stale > {archive_days} days")
        
        results['archived_agents'] = stale_agents
        
        # 2. Clean orphan locks
        from src.lock_cleanup import cleanup_stale_locks
        if not dry_run:
            lock_result = cleanup_stale_locks(max_age_seconds=300)
            results['cleaned_locks'] = lock_result.get('cleaned', 0)
        
        # 3. Fleet health summary
        results['fleet_health'] = self._compute_fleet_health()
        
        # 4. Export daily summary
        if not dry_run:
            results['export_path'] = self._export_daily_summary(results)
        
        return results
    
    def _compute_fleet_health(self) -> Dict[str, Any]:
        """Compute aggregate fleet health metrics."""
        try:
            from src.governance_monitor import GovernanceMonitor
            
            monitors = GovernanceMonitor.get_all_monitors()
            if not monitors:
                return {'status': 'no_agents', 'count': 0}
            
            coherences = []
            risks = []
            
            for agent_id, monitor in monitors.items():
                if hasattr(monitor, 'state'):
                    coherences.append(monitor.state.coherence)
                    if monitor.state.risk_history:
                        risks.append(monitor.state.risk_history[-1])
            
            return {
                'status': 'healthy' if (coherences and sum(coherences)/len(coherences) > 0.5) else 'degraded',
                'count': len(monitors),
                'mean_coherence': sum(coherences)/len(coherences) if coherences else 0,
                'mean_risk': sum(risks)/len(risks) if risks else 0,
            }
        except ImportError:
            return {'status': 'unavailable', 'reason': 'governance_monitor not loaded'}
    
    def _export_daily_summary(self, results: Dict[str, Any]) -> str:
        """Export daily maintenance summary."""
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"daily_summary_{date_str}.json"
        filepath = self.exports_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        return str(filepath)
    
    # ─────────────────────────────────────────────────────────────
    # WORKFLOW 3: Health Report (Single Artifact Out)
    # ─────────────────────────────────────────────────────────────
    
    def health_report(self, format: str = 'json') -> Dict[str, Any]:
        """
        Generate comprehensive health report as a single artifact.
        
        Combines:
        - health_check()
        - aggregate_metrics()
        - detect_anomalies()
        - calibration status
        - workspace health
        
        Into ONE exportable artifact instead of 5 separate tool calls.
        """
        report = {
            'generated_at': datetime.now().isoformat(),
            'version': '2.0.0',
            
            # Fleet metrics
            'fleet': self._compute_fleet_health(),
            
            # Calibration (defensive import)
            'calibration': self._get_calibration_status(),
            
            # Workspace (defensive import)
            'workspace': self._get_workspace_status(),
            
            # Anomalies (recent)
            'anomalies': self._detect_recent_anomalies(),
        }
        
        # Export
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"health_report_{timestamp}.{format}"
        filepath = self.exports_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        report['export_path'] = str(filepath)
        return report
    
    def _get_calibration_status(self) -> Dict[str, Any]:
        """Get calibration status with defensive import."""
        try:
            from src.calibration import calibration_checker
            return {
                'is_calibrated': calibration_checker.is_calibrated(),
                'accuracy': getattr(calibration_checker, 'accuracy', None),
                'confidence_mean': getattr(calibration_checker, 'mean_confidence', None),
                'sample_count': getattr(calibration_checker, 'sample_count', None),
            }
        except ImportError:
            return {'status': 'unavailable', 'reason': 'calibration module not loaded'}
    
    def _get_workspace_status(self) -> Dict[str, Any]:
        """Get workspace status with defensive import."""
        try:
            from src.workspace_health import get_workspace_health
            return get_workspace_health()
        except ImportError:
            return {'status': 'unavailable', 'reason': 'workspace_health module not loaded'}
    
    def _detect_recent_anomalies(self) -> List[Dict[str, Any]]:
        """Detect anomalies from recent history."""
        try:
            from src.governance_monitor import GovernanceMonitor
            
            anomalies = []
            monitors = GovernanceMonitor.get_all_monitors()
            
            for agent_id, monitor in monitors.items():
                state = monitor.state
                
                # Risk spike detection
                if len(state.risk_history) >= 3:
                    recent_risk = state.risk_history[-1]
                    baseline_risk = sum(state.risk_history[-10:-1]) / max(len(state.risk_history[-10:-1]), 1)
                    if recent_risk - baseline_risk > 0.15:
                        anomalies.append({
                            'agent_id': agent_id,
                            'type': 'risk_spike',
                            'current': recent_risk,
                            'baseline': baseline_risk,
                        })
                
                # Coherence drop detection
                if len(state.coherence_history) >= 3:
                    recent_coh = state.coherence_history[-1]
                    baseline_coh = sum(state.coherence_history[-10:-1]) / max(len(state.coherence_history[-10:-1]), 1)
                    if baseline_coh - recent_coh > 0.10:
                        anomalies.append({
                            'agent_id': agent_id,
                            'type': 'coherence_drop',
                            'current': recent_coh,
                            'baseline': baseline_coh,
                        })
            
            return anomalies
        except ImportError:
            return []
        
        return anomalies


# ─────────────────────────────────────────────────────────────────
# Singleton instance for easy access
# ─────────────────────────────────────────────────────────────────

_orchestrator: Optional[Orchestrator] = None

def get_orchestrator() -> Orchestrator:
    """Get or create the singleton orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
