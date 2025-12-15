#!/usr/bin/env python3
"""
Real-time Health Dashboard for UNITARES Governance MCP Server

Displays live system health metrics, agent status, and alerts.

Usage:
    python scripts/dashboard.py [--host HOST] [--port PORT] [--refresh SECONDS]

Example:
    python scripts/dashboard.py --host 127.0.0.1 --port 8765 --refresh 5
"""

import sys
import argparse
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import urllib.request
import urllib.error

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.logging_utils import get_logger

logger = get_logger(__name__)


class Dashboard:
    """Real-time health dashboard for monitoring MCP server"""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 8765, refresh_interval: int = 5):
        self.host = host
        self.port = port
        self.refresh_interval = refresh_interval
        self.base_url = f"http://{host}:{port}"
        self.alerts = []
    
    def fetch_json(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Fetch JSON from endpoint"""
        try:
            url = f"{self.base_url}{endpoint}"
            with urllib.request.urlopen(url, timeout=5) as response:
                return json.loads(response.read().decode())
        except urllib.error.URLError as e:
            logger.error(f"Failed to fetch {endpoint}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {endpoint}: {e}")
            return None
    
    def fetch_metrics(self) -> Optional[str]:
        """Fetch Prometheus metrics"""
        try:
            url = f"{self.base_url}/metrics"
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.read().decode()
        except Exception as e:
            logger.error(f"Error fetching metrics: {e}")
            return None
    
    def check_alerts(self, health_data: Dict[str, Any], metrics_data: Optional[str]) -> list:
        """Check for critical conditions and generate alerts"""
        alerts = []
        
        # Parse metrics if available
        metrics = {}
        if metrics_data:
            for line in metrics_data.split("\n"):
                if line and not line.startswith("#"):
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            metrics[parts[0]] = float(parts[1])
                        except ValueError:
                            pass
        
        # Check connection health
        if health_data:
            checks = health_data.get("checks", {})
            for check_name, check_data in checks.items():
                if isinstance(check_data, dict) and check_data.get("status") == "error":
                    alerts.append({
                        "severity": "critical",
                        "component": check_name,
                        "message": f"{check_name} is in error state",
                        "details": check_data.get("error", "Unknown error")
                    })
        
        # Check agent metrics
        if "unitares_agents_paused" in metrics:
            paused = int(metrics["unitares_agents_paused"])
            if paused > 5:
                alerts.append({
                    "severity": "warning",
                    "component": "agents",
                    "message": f"High number of paused agents: {paused}",
                    "details": "Consider investigating why agents are paused"
                })
        
        # Check active connections
        if "unitares_connections_active" in metrics:
            connections = int(metrics["unitares_connections_active"])
            if connections == 0:
                alerts.append({
                    "severity": "warning",
                    "component": "connections",
                    "message": "No active SSE connections",
                    "details": "Server may be idle or clients disconnected"
                })
            elif connections > 50:
                alerts.append({
                    "severity": "warning",
                    "component": "connections",
                    "message": f"High number of connections: {connections}",
                    "details": "May indicate connection leak or high load"
                })
        
        # Check knowledge graph size
        if "unitares_knowledge_graph_nodes" in metrics:
            nodes = int(metrics["unitares_knowledge_graph_nodes"])
            if nodes > 10000:
                alerts.append({
                    "severity": "info",
                    "component": "knowledge_graph",
                    "message": f"Large knowledge graph: {nodes} nodes",
                    "details": "Consider archiving old discoveries"
                })
        
        return alerts
    
    def format_status(self, status: str) -> str:
        """Format status with color codes"""
        colors = {
            "healthy": "\033[92m✓\033[0m",  # Green
            "moderate": "\033[93m⚠\033[0m",  # Yellow
            "error": "\033[91m✗\033[0m",    # Red
            "warning": "\033[93m⚠\033[0m"   # Yellow
        }
        return colors.get(status.lower(), "?")
    
    def display_dashboard(self, health_data: Optional[Dict[str, Any]], 
                         metrics_data: Optional[str], alerts: list):
        """Display formatted dashboard"""
        # Clear screen (works on most terminals)
        print("\033[2J\033[H", end="")
        
        print("=" * 80)
        print("UNITARES Governance MCP Server - Real-time Health Dashboard")
        print("=" * 80)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Server: {self.base_url}")
        print(f"Refresh: Every {self.refresh_interval} seconds")
        print("=" * 80)
        print()
        
        # Overall Health Status
        if health_data:
            overall_status = health_data.get("status", "unknown")
            print(f"Overall Status: {self.format_status(overall_status)} {overall_status.upper()}")
            print()
            
            # Component Health
            print("Component Health:")
            print("-" * 80)
            checks = health_data.get("checks", {})
            for check_name, check_data in sorted(checks.items()):
                if isinstance(check_data, dict):
                    status = check_data.get("status", "unknown")
                    print(f"  {self.format_status(status)} {check_name:<30} {status}")
            print()
        
        # Metrics Summary
        if metrics_data:
            print("Key Metrics:")
            print("-" * 80)
            metrics = {}
            for line in metrics_data.split("\n"):
                if line and not line.startswith("#"):
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            metrics[parts[0]] = float(parts[1])
                        except ValueError:
                            pass
            
            if "unitares_connections_active" in metrics:
                print(f"  Active Connections: {int(metrics['unitares_connections_active'])}")
            if "unitares_agents_active" in metrics:
                print(f"  Active Agents: {int(metrics['unitares_agents_active'])}")
            if "unitares_agents_paused" in metrics:
                print(f"  Paused Agents: {int(metrics['unitares_agents_paused'])}")
            if "unitares_monitors_active" in metrics:
                print(f"  Active Monitors: {int(metrics['unitares_monitors_active'])}")
            if "unitares_dialectic_sessions_active" in metrics:
                print(f"  Dialectic Sessions: {int(metrics['unitares_dialectic_sessions_active'])}")
            if "unitares_knowledge_graph_nodes" in metrics:
                print(f"  Knowledge Graph Nodes: {int(metrics['unitares_knowledge_graph_nodes'])}")
            if "unitares_tool_calls_total" in metrics:
                print(f"  Tool Calls (1h): {int(metrics['unitares_tool_calls_total'])}")
            print()
        
        # Alerts
        if alerts:
            print("Alerts:")
            print("-" * 80)
            for alert in alerts:
                severity = alert.get("severity", "info")
                component = alert.get("component", "unknown")
                message = alert.get("message", "No message")
                details = alert.get("details", "")
                
                severity_icon = {
                    "critical": "\033[91m🔴\033[0m",
                    "warning": "\033[93m🟡\033[0m",
                    "info": "\033[94m🔵\033[0m"
                }.get(severity, "⚪")
                
                print(f"  {severity_icon} [{severity.upper()}] {component}: {message}")
                if details:
                    print(f"      {details}")
            print()
        else:
            print("Alerts: None")
            print()
        
        print("=" * 80)
        print("Press Ctrl+C to exit")
        print("=" * 80)
    
    def run(self):
        """Run dashboard loop"""
        print("Starting dashboard...")
        print(f"Connecting to {self.base_url}")
        print()
        
        try:
            while True:
                # Fetch data
                health_data = self.fetch_json("/health")
                metrics_data = self.fetch_metrics()
                
                # Check for alerts
                alerts = self.check_alerts(health_data, metrics_data)
                
                # Display dashboard
                self.display_dashboard(health_data, metrics_data, alerts)
                
                # Wait for next refresh
                time.sleep(self.refresh_interval)
        
        except KeyboardInterrupt:
            print("\n\nDashboard stopped.")
        except Exception as e:
            logger.error(f"Dashboard error: {e}", exc_info=True)
            print(f"\nError: {e}")


def main():
    parser = argparse.ArgumentParser(description="UNITARES Governance MCP Server Dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Server port (default: 8765)")
    parser.add_argument("--refresh", type=int, default=5, help="Refresh interval in seconds (default: 5)")
    
    args = parser.parse_args()
    
    dashboard = Dashboard(host=args.host, port=args.port, refresh_interval=args.refresh)
    dashboard.run()


if __name__ == "__main__":
    main()

