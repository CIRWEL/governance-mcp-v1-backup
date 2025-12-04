#!/usr/bin/env python3
"""
Generate a comprehensive summary of bug statuses in the knowledge layer.
"""

import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge_layer import KnowledgeManager

def format_timestamp(ts: str) -> str:
    """Format ISO timestamp to readable date."""
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M')
    except:
        return ts[:10]

def get_agent_map(km: KnowledgeManager) -> dict:
    """Build timestamp -> agent_id mapping."""
    agent_map = {}
    for knowledge_file in km.data_dir.glob("*_knowledge.json"):
        agent_id_from_file = knowledge_file.stem.replace("_knowledge", "")
        knowledge = km.load_knowledge(agent_id_from_file)
        if knowledge:
            for disc in knowledge.discoveries:
                agent_map[disc.timestamp] = agent_id_from_file
    return agent_map

def main():
    km = KnowledgeManager()
    
    # Build agent mapping
    agent_map = get_agent_map(km)
    
    # Query all bugs
    all_bugs = km.query_discoveries(discovery_type="bug_found", sort_by="timestamp", sort_order="desc")
    
    # Group by status
    by_status = defaultdict(list)
    by_severity = defaultdict(lambda: defaultdict(int))
    by_agent = defaultdict(lambda: defaultdict(int))
    
    for bug in all_bugs:
        by_status[bug.status].append(bug)
        if bug.severity:
            by_severity[bug.status][bug.severity] += 1
        agent_id = agent_map.get(bug.timestamp, 'unknown')
        by_agent[bug.status][agent_id] += 1
    
    # Generate report
    report = []
    report.append("# Knowledge Layer Bug Status Summary")
    report.append(f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"\n**Total Bugs:** {len(all_bugs)}")
    report.append("\n---\n")
    
    # Summary statistics
    report.append("## 📊 Summary Statistics\n")
    report.append(f"- **Open:** {len(by_status.get('open', []))}")
    report.append(f"- **Resolved:** {len(by_status.get('resolved', []))}")
    report.append(f"- **Archived:** {len(by_status.get('archived', []))}")
    
    # Severity breakdown
    report.append("\n### By Severity\n")
    for status in ['open', 'resolved', 'archived']:
        bugs = by_status.get(status, [])
        if bugs:
            report.append(f"\n**{status.upper()}:**")
            severity_counts = defaultdict(int)
            for bug in bugs:
                if bug.severity:
                    severity_counts[bug.severity] += 1
            for sev in ['critical', 'high', 'medium', 'low']:
                count = severity_counts.get(sev, 0)
                if count > 0:
                    report.append(f"  - {sev}: {count}")
    
    # Open bugs detail
    open_bugs = by_status.get('open', [])
    if open_bugs:
        report.append("\n---\n")
        report.append("## 🔴 Open Bugs\n")
        report.append(f"**Total:** {len(open_bugs)}\n")
        
        # Group by severity
        open_by_severity = defaultdict(list)
        for bug in open_bugs:
            sev = bug.severity or 'unassigned'
            open_by_severity[sev].append(bug)
        
        for sev in ['critical', 'high', 'medium', 'low', 'unassigned']:
            bugs = open_by_severity.get(sev, [])
            if bugs:
                report.append(f"\n### {sev.upper()} Severity ({len(bugs)})\n")
                for i, bug in enumerate(bugs, 1):
                    agent_id = agent_map.get(bug.timestamp, 'unknown')
                    
                    report.append(f"{i}. **{bug.summary[:80]}...**")
                    report.append(f"   - Agent: `{agent_id}`")
                    report.append(f"   - Date: {format_timestamp(bug.timestamp)}")
                    if bug.tags:
                        report.append(f"   - Tags: {', '.join(bug.tags)}")
                    if bug.related_files:
                        report.append(f"   - Files: {', '.join(bug.related_files[:3])}")
                    report.append("")
    
    # Recently resolved bugs
    resolved_bugs = sorted(by_status.get('resolved', []), 
                          key=lambda b: b.resolved_at or b.timestamp, 
                          reverse=True)[:10]
    
    if resolved_bugs:
        report.append("\n---\n")
        report.append("## ✅ Recently Resolved Bugs\n")
        report.append(f"**Showing:** Last 10 of {len(by_status.get('resolved', []))} resolved\n")
        
        for i, bug in enumerate(resolved_bugs, 1):
            agent_id = agent_map.get(bug.timestamp, 'unknown')
            resolved_date = format_timestamp(bug.resolved_at) if bug.resolved_at else format_timestamp(bug.timestamp)
            report.append(f"{i}. **{bug.summary[:80]}...**")
            report.append(f"   - Agent: `{agent_id}`")
            report.append(f"   - Resolved: {resolved_date}")
            if bug.severity:
                report.append(f"   - Severity: {bug.severity}")
            report.append("")
    
    # Write report
    report_text = '\n'.join(report)
    output_file = Path(__file__).parent.parent / "docs" / "analysis" / "BUG_STATUS_SUMMARY.md"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(report_text)
    
    print("📊 Bug Status Summary Generated")
    print(f"📄 Saved to: {output_file}")
    print(f"\n{report_text}")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())

