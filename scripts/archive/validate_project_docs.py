#!/usr/bin/env python3
"""
Governance Project Documentation Validator

Prevents documentation drift by validating that onboarding docs accurately
reflect the current system state. Designed to prevent future Claude instances
from being confused by outdated documentation.

Usage:
    python3 scripts/validate_project_docs.py
    python3 scripts/validate_project_docs.py --report
    python3 scripts/validate_project_docs.py --verbose

Exit codes:
    0 - All checks passed
    1 - Critical issues found
    2 - Major issues found (warnings)
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

class Issue:
    def __init__(self, severity: str, category: str, file: str,
                 description: str, fix_hint: str = None):
        self.severity = severity  # critical, major, minor
        self.category = category
        self.file = file
        self.description = description
        self.fix_hint = fix_hint
        self.timestamp = datetime.now().isoformat()

    def __str__(self):
        severity_icon = {
            "critical": "🔴",
            "major": "🟠",
            "minor": "🟡"
        }[self.severity]

        result = f"{severity_icon} [{self.severity.upper()}] {self.description}\n"
        result += f"   File: {self.file}\n"
        if self.fix_hint:
            result += f"   Fix: {self.fix_hint}\n"
        return result


class GovernanceDocValidator:
    """Validates governance-mcp-v1 documentation completeness and accuracy."""

    def __init__(self, project_root: Path = None):
        if project_root is None:
            # Script is in scripts/archive/, so go up 2 levels to project root
            project_root = Path(__file__).parent.parent.parent
        self.project_root = project_root
        self.issues: List[Issue] = []
        self.checks_passed = 0
        self.checks_failed = 0
        self.verbose = False

    def log(self, message: str):
        """Print message if verbose mode."""
        if self.verbose:
            print(f"  {message}")

    def add_issue(self, severity: str, category: str, file: str,
                  description: str, fix_hint: str = None):
        """Add validation issue."""
        issue = Issue(severity, category, file, description, fix_hint)
        self.issues.append(issue)
        self.checks_failed += 1
        print(issue)

    def validate_all(self) -> int:
        """Run all validation checks. Returns exit code."""
        print("🔍 Validating governance-mcp-v1 documentation...\n")

        # Critical checks (exit 1 if fail)
        self.validate_core_architecture_documented()
        self.validate_onboarding_freshness()
        self.validate_deprecated_features_marked()

        # Major checks (exit 2 if fail, but no critical)
        self.validate_feature_coverage()
        self.validate_cross_references()
        self.validate_readme_current()
        self.validate_cli_exception_documented()

        # Minor checks (warnings only)
        self.validate_examples_work()
        self.validate_no_conflicting_info()
        self.validate_markdown_file_sizes()

        return self.print_summary()

    def validate_core_architecture_documented(self):
        """Check that core architectural components are documented."""
        print("🏗️  Checking core architecture documentation...")

        # Define what MUST be documented
        required_features = {
            "governance_core": {
                "files": ["README.md", "docs/reference/AI_ASSISTANT_GUIDE.md"],
                "keywords": ["governance_core", "canonical", "mathematical foundation"],
                "importance": "critical",
                "reason": "governance_core is the mathematical foundation (added Nov 22)"
            },
            "pure_coherence": {
                "files": ["README.md", "docs/reference/AI_ASSISTANT_GUIDE.md"],
                "keywords": ["pure C(V)", "coherence(V", "tanh"],
                "importance": "critical",
                "reason": "Pure coherence replaced parameter blend (major architectural change)"
            },
            "circuit_breaker": {
                "files": ["README.md", "docs/guides/ONBOARDING.md"],
                "keywords": ["circuit breaker", "paused", "enforcement"],
                "importance": "critical",
                "reason": "Circuit breakers provide enforcement (not just advisory)"
            },
            "dialectic_protocol": {
                "files": ["README.md", "docs/guides/ONBOARDING.md"],
                "keywords": ["dialectic", "thesis", "antithesis", "peer review"],
                "importance": "major",
                "reason": "Dialectic enables autonomous recovery (added Nov 25 by funk)"
            },
            "knowledge_layer": {
                "files": ["README.md", "docs/guides/ONBOARDING.md"],
                "keywords": ["knowledge layer", "store_knowledge", "discoveries"],
                "importance": "major",
                "reason": "Knowledge layer replaces ad-hoc documentation"
            }
        }

        for feature_name, config in required_features.items():
            documented_in = []
            for doc_file in config["files"]:
                full_path = self.project_root / doc_file
                if not full_path.exists():
                    continue

                content = full_path.read_text().lower()
                if any(keyword.lower() in content for keyword in config["keywords"]):
                    documented_in.append(doc_file)

            if not documented_in:
                severity = config["importance"]
                self.add_issue(
                    severity=severity,
                    category="missing_feature_docs",
                    file=", ".join(config["files"]),
                    description=f"{feature_name} not documented anywhere",
                    fix_hint=f"{config['reason']} - Add section explaining this feature"
                )
            else:
                self.checks_passed += 1
                self.log(f"✓ {feature_name} documented in: {', '.join(documented_in)}")

    def validate_onboarding_freshness(self):
        """Check that onboarding docs are recent (not stale)."""
        print("\n📅 Checking onboarding documentation freshness...")

        docs_to_check = [
            ("docs/reference/AI_ASSISTANT_GUIDE.md", 14),  # Should be updated every 2 weeks
            ("docs/guides/ONBOARDING.md", 30),  # Can be older if stable
            ("README.md", 7),  # Main docs should be fresh
        ]

        for doc_path, max_age_days in docs_to_check:
            full_path = self.project_root / doc_path
            if not full_path.exists():
                self.add_issue(
                    severity="critical",
                    category="missing_doc",
                    file=doc_path,
                    description=f"Critical onboarding doc missing: {doc_path}",
                    fix_hint="Create this file or update ONBOARDING.md to point elsewhere"
                )
                continue

            # Check for date markers in content
            content = full_path.read_text()

            # Look for "Created:" or "Updated:" dates
            date_patterns = [
                r'\*\*(?:Created|Last Updated|Updated|Date):\*\*\s*(\w+ \d{1,2},? \d{4})',
                r'\*\*(?:Created|Last Updated|Updated|Date):\*\*\s*(\d{4}-\d{2}-\d{2})',  # Bold with YYYY-MM-DD
                r'(?:Created|Last Updated|Updated|Date):\s*(\d{4}-\d{2}-\d{2})',  # No bold
                r'## .*\((\d{4}-\d{2}-\d{2})\)',
            ]

            found_dates = []
            for pattern in date_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                found_dates.extend(matches)

            if not found_dates:
                self.add_issue(
                    severity="major",
                    category="no_date_marker",
                    file=doc_path,
                    description=f"No date marker found in {doc_path}",
                    fix_hint="Add '**Last Updated:** {date}' header"
                )
                continue

            # Parse most recent date
            latest_date = None
            for date_str in found_dates:
                try:
                    # Try different formats
                    for fmt in ["%B %d, %Y", "%B %d %Y", "%Y-%m-%d"]:
                        try:
                            parsed = datetime.strptime(date_str, fmt)
                            if latest_date is None or parsed > latest_date:
                                latest_date = parsed
                            break
                        except ValueError:
                            continue
                except Exception:
                    continue

            if latest_date:
                age_days = (datetime.now() - latest_date).days
                if age_days > max_age_days:
                    severity = "critical" if age_days > max_age_days * 2 else "major"
                    self.add_issue(
                        severity=severity,
                        category="stale_doc",
                        file=doc_path,
                        description=f"{doc_path} is {age_days} days old (max: {max_age_days})",
                        fix_hint=f"Review and update, or mark sections as 'Last validated: {datetime.now().strftime('%Y-%m-%d')}'"
                    )
                else:
                    self.checks_passed += 1
                    self.log(f"✓ {doc_path} is fresh ({age_days} days old)")

    def validate_deprecated_features_marked(self):
        """Check that deprecated features are clearly marked."""
        print("\n🚫 Checking deprecated features are marked...")

        deprecated_features = {
            "param_coherence": {
                "replacement": "pure C(V) coherence",
                "should_appear_in": ["docs/reference/README_FOR_FUTURE_CLAUDES.md"],
                "must_be_marked": ["deprecated", "removed", "no longer"]
            },
            "128-parameter": {
                "replacement": "only first 6 dimensions meaningful",
                "should_appear_in": ["docs/reference/README_FOR_FUTURE_CLAUDES.md"],
                "must_be_marked": ["deprecated", "placeholder", "not used"]
            },
            "parameter blend": {
                "replacement": "pure thermodynamic C(V)",
                "should_appear_in": ["README.md", "docs/guides/METRICS_GUIDE.md"],
                "must_be_marked": ["removed", "replaced", "pure"]
            }
        }

        for feature, config in deprecated_features.items():
            for doc_file in config["should_appear_in"]:
                full_path = self.project_root / doc_file
                if not full_path.exists():
                    continue

                content = full_path.read_text().lower()

                # Check if feature is mentioned
                if feature.lower() in content:
                    # Check if it's marked as deprecated
                    # Look for the feature AND deprecation marker in nearby text
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if feature.lower() in line:
                            # Check surrounding lines (±3 lines)
                            context = '\n'.join(lines[max(0, i-3):min(len(lines), i+4)]).lower()
                            if not any(marker in context for marker in config["must_be_marked"]):
                                self.add_issue(
                                    severity="major",
                                    category="unmarked_deprecation",
                                    file=doc_file,
                                    description=f"'{feature}' mentioned but not marked as deprecated",
                                    fix_hint=f"Add note: '{feature} is deprecated. Use {config['replacement']} instead.'"
                                )
                                break
                    else:
                        self.checks_passed += 1
                        self.log(f"✓ {feature} properly marked as deprecated in {doc_file}")

    def validate_feature_coverage(self):
        """Check that features in code are documented."""
        print("\n📚 Checking feature documentation coverage...")

        # Check if major source files exist and are documented
        feature_files = {
            "src/dialectic_protocol.py": {
                "docs": ["docs/CIRCUIT_BREAKER_DIALECTIC.md", "README.md"],
                "min_mentions": 1
            },
            "governance_core/": {
                "docs": ["governance_core/README.md", "README.md"],
                "min_mentions": 1
            },
            "src/knowledge_layer.py": {
                "docs": ["docs/guides/KNOWLEDGE_LAYER_USAGE.md", "README.md"],
                "min_mentions": 1
            }
        }

        for feature_path, config in feature_files.items():
            full_feature_path = self.project_root / feature_path
            if not full_feature_path.exists():
                continue  # Feature doesn't exist, skip

            mentions = 0
            for doc_file in config["docs"]:
                doc_path = self.project_root / doc_file
                if doc_path.exists():
                    content = doc_path.read_text().lower()
                    if feature_path.lower() in content or Path(feature_path).stem in content:
                        mentions += 1

            if mentions < config["min_mentions"]:
                self.add_issue(
                    severity="major",
                    category="undocumented_feature",
                    file=feature_path,
                    description=f"{feature_path} exists but not documented in expected locations",
                    fix_hint=f"Add section to {config['docs'][0]} explaining this feature"
                )
            else:
                self.checks_passed += 1
                self.log(f"✓ {feature_path} documented ({mentions} mentions)")

    def validate_cross_references(self):
        """Check that cross-references between docs are valid."""
        print("\n🔗 Checking cross-references...")

        docs_to_check = [
            "README.md",
            "ONBOARDING.md",
            "docs/reference/README_FOR_FUTURE_CLAUDES.md"
        ]

        for doc_file in docs_to_check:
            full_path = self.project_root / doc_file
            if not full_path.exists():
                continue

            content = full_path.read_text()

            # Extract markdown links: [text](path)
            link_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
            links = re.findall(link_pattern, content)

            for link_text, link_path in links:
                # Skip external links
                if link_path.startswith('http'):
                    continue

                # Handle anchors in links (e.g., file.md#section)
                # Strip anchor part for file validation, but don't validate anchor itself
                original_link_path = link_path
                anchor = None
                if '#' in link_path:
                    link_path, anchor = link_path.split('#', 1)
                    # Skip pure anchor links (only #section with no file)
                    if not link_path:
                        continue

                # Resolve relative path
                if link_path.startswith('/'):
                    target = self.project_root / link_path.lstrip('/')
                else:
                    target = (self.project_root / doc_file).parent / link_path

                target = target.resolve()

                if not target.exists():
                    self.add_issue(
                        severity="major",
                        category="broken_link",
                        file=doc_file,
                        description=f"Broken link: [{link_text}]({original_link_path})",
                        fix_hint=f"Update link or create missing file: {target}"
                    )
                else:
                    self.checks_passed += 1
                    self.log(f"✓ Link valid: {original_link_path}")

    def validate_readme_current(self):
        """Check README.md reflects current system state."""
        print("\n📖 Checking README.md currency...")

        readme = self.project_root / "README.md"
        if not readme.exists():
            self.add_issue(
                severity="critical",
                category="missing_readme",
                file="README.md",
                description="README.md missing",
                fix_hint="Create README.md with current system overview"
            )
            return

        content = readme.read_text()

        # Check for version marker
        if "v2.1" not in content and "v2.0" not in content:
            self.add_issue(
                severity="major",
                category="no_version",
                file="README.md",
                description="No version marker found",
                fix_hint="Add version header: # UNITARES Governance Framework v2.1"
            )
        else:
            self.checks_passed += 1
            self.log("✓ Version marker present")

        # Check for architecture section
        if "architecture" not in content.lower():
            self.add_issue(
                severity="major",
                category="missing_architecture",
                file="README.md",
                description="No architecture section",
                fix_hint="Add ## Architecture section"
            )
        else:
            self.checks_passed += 1
            self.log("✓ Architecture section present")

    def validate_cli_exception_documented(self):
        """Check that Claude Code CLI's lack of MCP is documented."""
        print("\n🔌 Checking Claude Code CLI exception documented...")

        required_docs = ["README.md", "docs/reference/AI_ASSISTANT_GUIDE.md"]

        for doc_file in required_docs:
            full_path = self.project_root / doc_file
            if not full_path.exists():
                continue

            content = full_path.read_text().lower()

            # Check if CLI exception is mentioned
            cli_keywords = ["claude code cli", "claude cli", "no mcp"]
            cli_mentioned = any(keyword in content for keyword in cli_keywords)

            # Check if MCP as standard is mentioned
            mcp_keywords = ["mcp protocol", "mcp native", "direct access"]
            mcp_standard_mentioned = any(keyword in content for keyword in mcp_keywords)

            # Check if bridge is mentioned for CLI
            bridge_keywords = ["bridge", "claude_code_bridge", "agent_self_log"]
            bridge_mentioned = any(keyword in content for keyword in bridge_keywords)

            if not cli_mentioned or not bridge_mentioned:
                self.add_issue(
                    severity="major",
                    category="missing_cli_exception",
                    file=doc_file,
                    description="Claude Code CLI's lack of MCP not clearly documented",
                    fix_hint="Add section: 'Claude Code CLI (exception): no MCP, use bridge script'"
                )
            elif not mcp_standard_mentioned:
                self.add_issue(
                    severity="minor",
                    category="missing_mcp_standard",
                    file=doc_file,
                    description="MCP as standard access method not clearly stated",
                    fix_hint="Add section: 'Most AIs use MCP directly (Desktop, Cursor, etc.)'"
                )
            else:
                self.checks_passed += 1
                self.log(f"✓ CLI exception and MCP standard documented in {doc_file}")

    def validate_examples_work(self):
        """Check that code examples in docs are valid."""
        print("\n💻 Checking code examples...")

        docs_with_examples = [
            "README.md",
            "docs/reference/README_FOR_FUTURE_CLAUDES.md",
            "ONBOARDING.md"
        ]

        for doc_file in docs_with_examples:
            full_path = self.project_root / doc_file
            if not full_path.exists():
                continue

            content = full_path.read_text()

            # Extract Python code blocks
            code_blocks = re.findall(r'```python\n(.*?)```', content, re.DOTALL)

            for block in code_blocks:
                # Check for common issues
                if "import" in block and "from governance_core" in block:
                    # Verify governance_core exists
                    if not (self.project_root / "governance_core" / "__init__.py").exists():
                        self.add_issue(
                            severity="minor",
                            category="invalid_example",
                            file=doc_file,
                            description="Example imports governance_core but module not found",
                            fix_hint="Update example or ensure governance_core/ exists"
                        )
                    else:
                        self.checks_passed += 1
                        self.log(f"✓ governance_core import example valid")

    def validate_no_conflicting_info(self):
        """Check for conflicting information across docs."""
        print("\n⚠️  Checking for conflicting information...")

        # Check coherence expectations
        docs_mentioning_coherence = []
        for doc_file in ["README.md", "docs/reference/README_FOR_FUTURE_CLAUDES.md", "docs/guides/METRICS_GUIDE.md"]:
            full_path = self.project_root / doc_file
            if not full_path.exists():
                continue

            content = full_path.read_text()

            # Look for coherence range claims
            if "0.85-0.95" in content or "0.85" in content:
                docs_mentioning_coherence.append((doc_file, "high (0.85+)"))
            if "0.49" in content or "~0.5" in content or "equilibrium" in content.lower():
                docs_mentioning_coherence.append((doc_file, "equilibrium (~0.5)"))

        # Check if there are conflicting claims
        high_claims = [d for d, t in docs_mentioning_coherence if "high" in t]
        eq_claims = [d for d, t in docs_mentioning_coherence if "equilibrium" in t]

        if high_claims and eq_claims:
            self.add_issue(
                severity="major",
                category="conflicting_info",
                file=", ".join(high_claims),
                description="Conflicting coherence expectations: some docs say 0.85+, others say ~0.5 is normal",
                fix_hint="Update old docs to explain: coherence ~0.49 at equilibrium is CORRECT (pure C(V))"
            )
        else:
            self.checks_passed += 1
            self.log("✓ No conflicting coherence expectations")

    def validate_markdown_file_sizes(self):
        """Check for markdown files that are too small and should use knowledge layer instead."""
        print("\n📄 Checking markdown file sizes...")
        
        # Essential docs that should stay as markdown regardless of size
        essential_docs = {
            'README.md', 'ONBOARDING.md', 'SYSTEM_SUMMARY.md', 'USAGE_GUIDE.md',
            'ARCHITECTURE.md', 'QUICK_REFERENCE.md', 'CHANGELOG.md',
            'DOCUMENTATION_GUIDELINES.md', 'DOC_MAP.md', 'ORGANIZATION_GUIDE.md',
            'SECURITY_AUDIT.md', 'RELEASE_NOTES_v2.0.md', 'ROADMAP_TO_10_10.md',
            'HANDOFF.md', 'END_TO_END_FLOW.md', 'AUTOMATIC_RECOVERY.md',
            'CIRCUIT_BREAKER_DIALECTIC.md', 'DIALECTIC_COORDINATION.md',
            'DIALECTIC_IMPROVEMENTS.md', 'CONFIDENCE_GATING_AND_CALIBRATION.md',
            'BACKUP_STRATEGY.md', 'DOCUMENTATION_COHERENCE.md', 'META_PATTERNS.md',
            'AGI_FRIENDLINESS_ASSESSMENT.md', 'AGI_FRIENDLINESS_IMPROVEMENTS.md',
            'authentication-guide.md', 'knowledge-layer.md'
        }
        
        # Threshold: 1000 words ≈ 5000 characters (rough estimate)
        WORD_THRESHOLD = 1000
        CHAR_THRESHOLD = 5000
        
        docs_dir = self.project_root / 'docs'
        if not docs_dir.exists():
            self.checks_passed += 1
            return
        
        small_files = []
        for md_file in docs_dir.rglob('*.md'):
            # Skip essential docs
            if md_file.name in essential_docs:
                continue
            
            # Skip archive (already archived)
            if 'archive' in md_file.parts:
                continue
            
            # Skip guides (comprehensive reference docs)
            if md_file.parent.name == 'guides':
                continue
            
            # Skip architecture docs (comprehensive)
            if md_file.parent.name == 'architecture':
                continue
            
            # Skip reference docs (comprehensive)
            if md_file.parent.name == 'reference':
                continue
            
            # Count words (rough estimate)
            content = md_file.read_text(encoding='utf-8', errors='ignore')
            word_count = len(content.split())
            char_count = len(content)
            
            # If under threshold, flag it
            if word_count < WORD_THRESHOLD and char_count < CHAR_THRESHOLD:
                rel_path = md_file.relative_to(self.project_root)
                small_files.append((rel_path, word_count, char_count))
        
        if small_files:
            for rel_path, word_count, char_count in small_files[:10]:  # Limit to 10 examples
                self.add_issue(
                    severity="minor",
                    category="markdown_size",
                    file=str(rel_path),
                    description=f"Small markdown file ({word_count} words, {char_count} chars) - consider using knowledge layer instead",
                    fix_hint=f"Use store_knowledge() for discrete discoveries, or expand to 1000+ words for comprehensive report. See docs/DOCUMENTATION_GUIDELINES.md"
                )
            
            if len(small_files) > 10:
                self.add_issue(
                    severity="minor",
                    category="markdown_size",
                    file="docs/",
                    description=f"Found {len(small_files)} small markdown files - consider migrating to knowledge layer",
                    fix_hint="Run: python3 scripts/check_small_markdowns.py --suggest-migration"
                )
        else:
            self.checks_passed += 1
            self.log("✓ All markdown files are appropriately sized")

    def print_summary(self) -> int:
        """Print validation summary and return exit code."""
        print(f"\n{'='*70}")
        print(f"📋 Validation Summary")
        print(f"{'='*70}")
        print(f"✅ Checks passed: {self.checks_passed}")
        print(f"❌ Checks failed: {self.checks_failed}")
        print(f"📊 Total issues: {len(self.issues)}")

        if self.issues:
            # Count by severity
            critical = len([i for i in self.issues if i.severity == "critical"])
            major = len([i for i in self.issues if i.severity == "major"])
            minor = len([i for i in self.issues if i.severity == "minor"])

            print(f"\n🔍 Issues by severity:")
            if critical:
                print(f"  🔴 Critical: {critical}")
            if major:
                print(f"  🟠 Major: {major}")
            if minor:
                print(f"  🟡 Minor: {minor}")

            # Determine exit code
            if critical > 0:
                print(f"\n❌ VALIDATION FAILED (critical issues)")
                return 1
            elif major > 0:
                print(f"\n⚠️  VALIDATION WARNING (major issues)")
                return 2
            else:
                print(f"\n⚠️  VALIDATION WARNING (minor issues)")
                return 0
        else:
            print(f"\n✅ ALL CHECKS PASSED!")
            return 0

    def generate_report(self, output_file: str = None):
        """Generate detailed validation report."""
        if output_file is None:
            output_file = str(self.project_root / "docs" / "PROJECT_DOCS_VALIDATION.md")

        report = f"""# Project Documentation Validation Report

**Generated:** {datetime.now().strftime("%B %d, %Y at %H:%M:%S")}
**Project:** governance-mcp-v1

## Purpose

This report validates that onboarding documentation accurately reflects the
current system state, preventing future Claude instances from being confused
by outdated or incomplete documentation.

## Summary

- ✅ Checks passed: {self.checks_passed}
- ❌ Checks failed: {self.checks_failed}
- 📊 Total issues: {len(self.issues)}

## Issues Found

"""

        if not self.issues:
            report += "*No issues found! Documentation is accurate and current.* ✨\n"
        else:
            for severity in ['critical', 'major', 'minor']:
                issues_of_severity = [i for i in self.issues if i.severity == severity]
                if not issues_of_severity:
                    continue

                report += f"\n### {severity.capitalize()} Issues ({len(issues_of_severity)})\n\n"

                for issue in issues_of_severity:
                    report += f"#### {issue.description}\n\n"
                    report += f"**File:** `{issue.file}`\n"
                    report += f"**Category:** {issue.category}\n"
                    if issue.fix_hint:
                        report += f"**Fix:** {issue.fix_hint}\n"
                    report += f"\n---\n\n"

        report += f"""
## Validation Checks Performed

1. ✅ Core architecture documented (governance_core, pure coherence, circuit breakers)
2. ✅ Onboarding documentation freshness (<14 days for critical docs)
3. ✅ Deprecated features clearly marked
4. ✅ Feature documentation coverage (code → docs mapping)
5. ✅ Cross-references valid (no broken links)
6. ✅ README.md currency (version, architecture sections)
7. ✅ Code examples work (valid imports, existing paths)
8. ✅ No conflicting information (coherence expectations, etc.)
9. ✅ Markdown file sizes appropriate (warns on small files that should use knowledge layer)

## Recommendations

"""

        if len([i for i in self.issues if i.severity == "critical"]) > 0:
            report += "**URGENT:** Fix critical issues immediately. System documentation is significantly out of date.\n\n"

        if len([i for i in self.issues if i.severity == "major"]) > 0:
            report += "**IMPORTANT:** Address major issues soon. New users will be confused by current documentation.\n\n"

        report += """
## How to Fix

1. Run validator regularly: `python3 scripts/validate_project_docs.py`
2. Update docs when making architectural changes
3. Mark deprecated features clearly
4. Keep README_FOR_FUTURE_CLAUDES.md fresh (<14 days)
5. Cross-link major features between docs

---

*Generated by validate_project_docs.py*
"""

        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        Path(output_file).write_text(report)
        print(f"\n📄 Report written to: {output_file}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate governance-mcp-v1 documentation completeness"
    )
    parser.add_argument("--report", action="store_true",
                       help="Generate detailed markdown report")
    parser.add_argument("--verbose", action="store_true",
                       help="Show detailed progress")
    args = parser.parse_args()

    validator = GovernanceDocValidator()
    validator.verbose = args.verbose

    exit_code = validator.validate_all()

    if args.report:
        validator.generate_report()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
