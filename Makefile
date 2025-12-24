# Makefile for governance-mcp-v1 automation
.PHONY: help docs changelog install-hooks test test-quick clean

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

docs: ## Generate tool documentation from @mcp_tool decorators
	@echo "📝 Generating tool documentation..."
	@python3 scripts/generate_tool_docs.py

update-readme: ## Update README.md metadata (version, counts, date)
	@echo "📝 Updating README metadata..."
	@python3 scripts/update_readme_metadata.py

sync-bridge: ## Sync bridge script with MCP (tool count, terminology)
	@echo "🔄 Syncing bridge script with MCP..."
	@python3 scripts/sync_bridge_with_mcp.py

changelog: ## Update CHANGELOG.md from git commits (dry-run by default)
	@echo "📝 Generating changelog (dry-run)..."
	@python3 scripts/update_changelog.py --dry-run

changelog-update: ## Update CHANGELOG.md and VERSION file
	@echo "📝 Updating CHANGELOG.md and VERSION..."
	@python3 scripts/update_changelog.py

install-hooks: ## Install git pre-commit hooks (combined: docs + markdown checks)
	@echo "🔧 Installing pre-commit hooks..."
	@chmod +x scripts/pre-commit-combined
	@ln -sf ../../scripts/pre-commit-combined .git/hooks/pre-commit
	@echo "✅ Pre-commit hook installed (combined: auto-docs + markdown checks)"
	@echo "   - Documentation auto-generates when handler files change"
	@echo "   - Markdown proliferation checks run on new .md files"

uninstall-hooks: ## Uninstall git pre-commit hooks
	@echo "🗑️  Removing pre-commit hooks..."
	@rm -f .git/hooks/pre-commit
	@echo "✅ Pre-commit hook removed"

test: ## Run pytest with coverage
	@echo "🧪 Running tests with coverage..."
	@pytest

test-quick: ## Run pytest without coverage (override pytest.ini addopts)
	@echo "🧪 Running tests without coverage..."
	@pytest -o addopts=

test-unit: ## Run unit tests only (no coverage)
	@echo "🧪 Running unit tests..."
	@pytest --no-cov

test-coverage: ## Run tests and show coverage report
	@echo "🧪 Running tests with coverage report..."
	@pytest --cov-report=term-missing --cov-report=html
	@echo ""
	@echo "📊 Coverage report generated in htmlcov/index.html"

test-automation: ## Test all automation scripts
	@echo "🧪 Testing tool documentation generator..."
	@python3 scripts/generate_tool_docs.py
	@echo ""
	@echo "🧪 Testing README metadata updater..."
	@python3 scripts/update_readme_metadata.py --dry-run
	@echo ""
	@echo "🧪 Testing bridge sync..."
	@python3 scripts/sync_bridge_with_mcp.py --dry-run
	@echo ""
	@echo "🧪 Testing changelog generator..."
	@python3 scripts/update_changelog.py --dry-run

clean: ## Remove generated files
	@echo "🗑️  Cleaning up..."
	@# Add any cleanup tasks here

# Development workflow shortcuts
dev-docs: docs ## Alias for 'docs'

dev-changelog: changelog ## Alias for 'changelog'

# Quick command to update everything
update-all: docs update-readme sync-bridge changelog-update ## Update docs, README, bridge, and changelog
	@echo "✅ All documentation and bridge updated"
