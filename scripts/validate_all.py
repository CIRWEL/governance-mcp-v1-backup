#!/usr/bin/env python3
"""
Consolidated validation script - validates both project docs and layer consistency.

Usage:
    python3 scripts/validate_all.py              # Run all validations
    python3 scripts/validate_all.py --docs-only   # Only project docs
    python3 scripts/validate_all.py --layers-only # Only layer consistency
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import both validators (from archive since they're archived but still needed)
archive_path = Path(__file__).parent / "archive"
sys.path.insert(0, str(archive_path))
from validate_project_docs import GovernanceDocValidator
from validate_layer_consistency import validate_all_layers


def main():
    """Run all validation checks."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Validate project documentation and layer consistency')
    parser.add_argument('--docs-only', action='store_true', help='Only validate project docs')
    parser.add_argument('--layers-only', action='store_true', help='Only validate layer consistency')
    parser.add_argument('--report', action='store_true', help='Generate detailed report')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    exit_code = 0
    
    # Validate project docs
    if not args.layers_only:
        print("="*70)
        print("PROJECT DOCUMENTATION VALIDATION")
        print("="*70)
        validator = GovernanceDocValidator(project_root)
        validator.verbose = args.verbose
        doc_exit = validator.validate_all()
        if doc_exit > 0:
            exit_code = max(exit_code, doc_exit)
        print()
    
    # Validate layer consistency
    if not args.docs_only:
        print("="*70)
        print("LAYER CONSISTENCY VALIDATION")
        print("="*70)
        layer_result = validate_all_layers()
        if not layer_result:
            exit_code = max(exit_code, 1)
        print()
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()

