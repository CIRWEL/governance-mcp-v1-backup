"""
UNITARES Orchestrator v0.2.0 - Composable Workflows (Fixed)

Fixed version that properly integrates with the MCP layer:
- Uses correct API (monitors dict, verify_agent_ownership, UNITARESMonitor)
- Validates API keys
- Composes MCP handlers instead of reimplementing

Design Principles:
1. Log on thermodynamic significance, not routine
2. Export flows OUT, not just metrics IN
3. Single entry points for common operations
4. Self-cleaning: entropy out, not just in

Version: 0.2.0
Date: 2025-11-29
"""

from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import json
import sys

# Add project root
from src._imports import ensure_project_root
project_root = ensure_project_root()


class Orchestrator:
    """
    High-level workflows for governance operations.
    
    Composes existing MCP infrastructure into meaningful operations
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
        ethical_drift: Optional[List[float]] = None,
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
        # Import here to avoid circular imports
        from src.mcp_server_std import (
            monitors, agent_metadata, 
            verify_agent_ownership, get_or_create_metadata,
            save_monitor_state, save_metadata
        )
        from src.governance_monitor import UNITARESMonitor
        
        # 1. Validate API key (SECURITY)
        if agent_id in agent_metadata:
            is_valid, error = verify_agent_ownership(agent_id, api_key)
            if not is_valid:
                return {
                    'success': False,
                    'error': error,
                    'decision': None,
                    'metrics': None,
                }
        
        # 2. Get or create monitor (use correct API)
        metadata = get_or_create_metadata(agent_id)
        
        if agent_id not in monitors:
            monitors[agent_id] = UNITARESMonitor(agent_id=agent_id)
        
        monitor = monitors[agent_id]
        
        # 3. Capture previous state for significance check
        prev_risk = monitor.state.risk_history[-1] if monitor.state.risk_history else 0
        prev_coherence = monitor.state.coherence
        
        # 4. Run the update
        result = monitor.update(
            complexity=complexity,
            delta_eta=ethical_drift or [0.0, 0.0, 0.0],
            response_text=response_text,
        )
        
        # 5. Save state
        save_monitor_state(agent_id, monitor)
        metadata.last_update = datetime.now().isoformat()
        metadata.total_updates += 1
        save_metadata()
        
        # 6. Check thermodynamic significance
        significance = self._assess_significance(
            monitor=monitor,
            prev_risk=prev_risk,
            prev_coherence=prev_coherence,
            result=result,
        )
        
        # 7. Auto-export if significant
        export_result = None
        if auto_export and significance['is_significant']:
            export_result = self._export_significant_event(
                agent_id=agent_id,
                result=result,
                significance=significance,
            )
        
        return {
            'success': True,
            'decision': result.get('decision'),
            'metrics': result.get('metrics'),
            'significance': significance,
            'exported': export_result is not None,
            'export_path': export_result.get('file_path') if export_result else None,
        }
    
    def _assess_significance(
        self, 
        monitor,
        prev_risk: float,
        prev_coherence: float,
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
        current_risk = metrics.get('risk_score', 0)
        risk_delta = current_risk - prev_risk
        if risk_delta > self.significance_thresholds['risk_spike']:
            reasons.append(f"risk_spike: +{risk_delta:.3f}")
        
        # Check coherence drop
        current_coherence = metrics.get('coherence', 1)
        coh_delta = prev_coherence - current_coherence
        if coh_delta > self.significance_thresholds['coherence_drop']:
            reasons.append(f"coherence_drop: -{coh_delta:.3f}")
        
        # Check void threshold
        V = state.V
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
        1. Archive stale test/demo agents (inactive > archive_days)
        2. Clean orphan lock files
        3. Generate fleet health summary
        4. Export summary artifact
        """
        from src.mcp_server_std import agent_metadata, save_metadata
        from src.lock_cleanup import cleanup_stale_state_locks
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'dry_run': dry_run,
            'archived_agents': [],
            'cleaned_locks': 0,
            'fleet_health': {},
            'export_path': None,
        }
        
        # 1. Archive stale test/demo agents
        cutoff = datetime.now() - timedelta(days=archive_days)
        stale_agents = []
        
        for agent_id, meta in agent_metadata.items():
            last_update = meta.last_update
            if last_update:
                try:
                    last_dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                    if last_dt.replace(tzinfo=None) < cutoff:
                        # Only archive test/demo agents, not production
                        if any(x in agent_id.lower() for x in ['test', 'demo', 'tmp']):
                            if meta.status == 'active':
                                stale_agents.append(agent_id)
                except ValueError:
                    pass  # Skip if date parsing fails
        
        if not dry_run:
            for agent_id in stale_agents:
                meta = agent_metadata[agent_id]
                meta.status = 'archived'
                meta.archived_at = datetime.now().isoformat()
                meta.add_lifecycle_event('archived', f"Stale > {archive_days} days (auto)")
            if stale_agents:
                save_metadata()
        
        results['archived_agents'] = stale_agents
        
        # 2. Clean orphan locks
        if not dry_run:
            try:
                lock_result = cleanup_stale_state_locks(max_age_seconds=300)
                results['cleaned_locks'] = lock_result.get('cleaned', 0)
            except Exception as e:
                results['cleaned_locks'] = f"error: {e}"
        
        # 3. Fleet health summary
        results['fleet_health'] = self._compute_fleet_health()
        
        # 4. Export daily summary
        if not dry_run:
            results['export_path'] = self._export_daily_summary(results)
        
        return results
    
    def _compute_fleet_health(self) -> Dict[str, Any]:
        """Compute aggregate fleet health metrics."""
        from src.mcp_server_std import monitors, agent_metadata
        
        if not monitors:
            return {'status': 'no_monitors_loaded', 'count': 0}
        
        coherences = []
        risks = []
        active_count = 0
        
        for agent_id, monitor in monitors.items():
            meta = agent_metadata.get(agent_id)
            if meta and meta.status == 'active':
                active_count += 1
                coherences.append(monitor.state.coherence)
                if monitor.state.risk_history:
                    risks.append(monitor.state.risk_history[-1])
        
        mean_coherence = sum(coherences)/len(coherences) if coherences else 0
        mean_risk = sum(risks)/len(risks) if risks else 0
        
        # Determine status based on thermodynamics
        if mean_coherence > 0.5 and mean_risk < 0.4:
            status = 'healthy'
        elif mean_coherence > 0.4 or mean_risk < 0.6:
            status = 'moderate'
        else:
            status = 'critical'
        
        return {
            'status': status,
            'monitors_loaded': len(monitors),
            'active_agents': active_count,
            'mean_coherence': round(mean_coherence, 4),
            'mean_risk': round(mean_risk, 4),
        }
    
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
        
        Combines fleet metrics, calibration, and anomaly detection
        into ONE exportable artifact.
        """
        from src.calibration import calibration_checker
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'version': '2.0.0',
            
            # Fleet metrics
            'fleet': self._compute_fleet_health(),
            
            # Calibration status
            'calibration': {
                'is_calibrated': calibration_checker.is_calibrated() if hasattr(calibration_checker, 'is_calibrated') else False,
                'sample_count': getattr(calibration_checker, 'sample_count', 0),
            },
            
            # Recent anomalies
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
    
    def _detect_recent_anomalies(self) -> List[Dict[str, Any]]:
        """Detect anomalies from loaded monitors."""
        from src.mcp_server_std import monitors
        
        anomalies = []
        
        for agent_id, monitor in monitors.items():
            state = monitor.state
            
            # Risk spike detection
            if len(state.risk_history) >= 3:
                recent_risk = state.risk_history[-1]
                history_slice = state.risk_history[-10:-1] if len(state.risk_history) > 1 else []
                if history_slice:
                    baseline_risk = sum(history_slice) / len(history_slice)
                    if recent_risk - baseline_risk > 0.15:
                        anomalies.append({
                            'agent_id': agent_id,
                            'type': 'risk_spike',
                            'current': round(recent_risk, 4),
                            'baseline': round(baseline_risk, 4),
                            'delta': round(recent_risk - baseline_risk, 4),
                        })
            
            # Coherence drop detection
            if len(state.coherence_history) >= 3:
                recent_coh = state.coherence_history[-1]
                history_slice = state.coherence_history[-10:-1] if len(state.coherence_history) > 1 else []
                if history_slice:
                    baseline_coh = sum(history_slice) / len(history_slice)
                    if baseline_coh - recent_coh > 0.10:
                        anomalies.append({
                            'agent_id': agent_id,
                            'type': 'coherence_drop',
                            'current': round(recent_coh, 4),
                            'baseline': round(baseline_coh, 4),
                            'delta': round(baseline_coh - recent_coh, 4),
                        })
        
        return anomalies


# ─────────────────────────────────────────────────────────────────
# Singleton instance
# ─────────────────────────────────────────────────────────────────

_orchestrator: Optional[Orchestrator] = None

def get_orchestrator() -> Orchestrator:
    """Get or create the singleton orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
