"""Application/service layer (§7). Orchestrates core modules; no UI, no sqlite3."""

from mediavault.services.scanner import scan_roots

__all__ = ["scan_roots"]
