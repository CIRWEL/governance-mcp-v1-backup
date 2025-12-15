"""
API Key Management - Secure Storage with Smart Confirmation

Provides secure storage and retrieval of governance API keys with context tracking
to prevent identity confusion between agents.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import sys


class APIKeyManager:
    """Manages secure storage and retrieval of governance API keys"""

    def __init__(self, keystore_path: Optional[Path] = None):
        """
        Initialize API Key Manager

        Args:
            keystore_path: Path to keystore file (default: ~/.governance/api_keys.json)
        """
        if keystore_path is None:
            keystore_path = Path.home() / ".governance" / "api_keys.json"

        self.keystore_path = Path(keystore_path)
        self.keystore_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Ensure keystore has restrictive permissions
        if self.keystore_path.exists():
            os.chmod(self.keystore_path, 0o600)

    def store_key(self,
                  agent_id: str,
                  api_key: str,
                  context: Optional[Dict[str, Any]] = None) -> None:
        """
        Store an API key with context

        Args:
            agent_id: Agent identifier
            api_key: API key to store
            context: Optional context (user, hostname, working_dir, etc.)
        """
        keys = self._load_keys()

        if context is None:
            context = {}

        # Add metadata
        context.update({
            "created": datetime.now().isoformat(),
            "last_used": datetime.now().isoformat(),
            "user": os.getenv('USER', os.getenv('USERNAME', 'unknown')),
            "hostname": os.uname().nodename if hasattr(os, 'uname') else 'unknown',
            "working_dir": os.getcwd()
        })

        keys[agent_id] = {
            "api_key": api_key,
            "context": context
        }

        self._save_keys(keys)

    def get_key(self,
                agent_id: str,
                interactive: bool = True,
                auto_confirm: bool = False) -> Optional[str]:
        """
        Retrieve an API key with smart confirmation

        Args:
            agent_id: Agent identifier
            interactive: If True, show confirmation prompt
            auto_confirm: If True, skip confirmation (use with caution)

        Returns:
            API key if found and confirmed, None otherwise
        """
        keys = self._load_keys()

        if agent_id not in keys:
            return None

        entry = keys[agent_id]
        api_key = entry["api_key"]
        context = entry["context"]

        # Update last_used timestamp
        context["last_used"] = datetime.now().isoformat()
        self._save_keys(keys)

        # Show confirmation if interactive
        if interactive and not auto_confirm:
            print(f"\n🔑 Found stored API key for: {agent_id}")
            print(f"   Created: {context.get('created', 'unknown')}")
            print(f"   Last used: {context.get('last_used', 'unknown')}")
            print(f"   User: {context.get('user', 'unknown')} @ {context.get('hostname', 'unknown')}")

            if sys.stdin.isatty():
                response = input("\n   Use this key? [Y/n]: ").strip().lower()
                if response == 'n':
                    return None
            else:
                # Non-interactive but confirmation requested - auto-use
                print("   (Non-interactive mode - using stored key)")

        return api_key

    def remove_key(self, agent_id: str) -> bool:
        """
        Remove a stored API key

        Args:
            agent_id: Agent identifier

        Returns:
            True if key was removed, False if not found
        """
        keys = self._load_keys()

        if agent_id in keys:
            del keys[agent_id]
            self._save_keys(keys)
            return True

        return False

    def list_keys(self) -> Dict[str, Dict[str, Any]]:
        """
        List all stored keys with their context (excluding actual key values)

        Returns:
            Dictionary of agent_id -> context
        """
        keys = self._load_keys()

        return {
            agent_id: {
                "context": entry["context"],
                "has_key": bool(entry.get("api_key"))
            }
            for agent_id, entry in keys.items()
        }

    def _load_keys(self) -> Dict[str, Dict[str, Any]]:
        """Load keys from keystore file"""
        if not self.keystore_path.exists():
            return {}

        try:
            with open(self.keystore_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_keys(self, keys: Dict[str, Dict[str, Any]]) -> None:
        """Save keys to keystore file with restrictive permissions"""
        with open(self.keystore_path, 'w') as f:
            json.dump(keys, f, indent=2)

        # Ensure restrictive permissions
        os.chmod(self.keystore_path, 0o600)
